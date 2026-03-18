"""
monocle/agents/routing.py — RoutingAgent.

Two-tier routing strategy:

1. **Fast path (synchronous, no LLM call):** each template schema declares a
   ``sentence_starters`` list.  If the input text begins with any starter the
   matching template is returned immediately with ``fast_path=True``.

2. **Slow path (LLM call):** if no starter matches, the routing agent calls
   ``AIProvider.chat`` with the ``prompts/routing.md`` system prompt and
   parses a structured JSON response ``{template, confidence, rationale}``.
   If confidence < 0.6 the ``blank`` template is returned regardless.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from monocle.models import RoutingDecision

if TYPE_CHECKING:
    from monocle.ai.base import AIProvider

logger = logging.getLogger(__name__)

# Map template names → note_type (from template YAML note_type field)
_TEMPLATE_NOTE_TYPES: dict[str, str] = {
    "person": "person_note",
    "decision": "decision",
    "project": "project",
    "meeting": "meeting_note",
    "idea": "idea",
    "observation": "observation",
    "reference": "reference",
    "action_item": "action_item",
    "weekly_summary": "weekly_summary",
    "blank": "other",
}


def _load_all_templates() -> list[dict[str, Any]]:
    """Load all YAML template schemas from ``monocle/vault/templates/``."""
    template_dir = Path(__file__).parent.parent / "vault" / "templates"
    templates: list[dict[str, Any]] = []
    for yaml_file in sorted(template_dir.glob("*.yaml")):
        try:
            with open(yaml_file, encoding="utf-8") as fh:
                schema = yaml.safe_load(fh) or {}
            if "template" in schema:
                templates.append(schema)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RoutingAgent: could not load template %s: %s", yaml_file.name, exc)
    return templates


def _parse_routing_response(raw: str) -> dict[str, Any]:
    """Extract a JSON object from the LLM routing response."""
    stripped = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    stripped = re.sub(r"```\s*$", "", stripped, flags=re.MULTILINE).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        # Use greedy match so nested objects (e.g. {"meta": {...}}) are captured fully.
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


class RoutingAgent:
    """Dispatch raw content to the appropriate note template.

    Args:
        ai: ``AIProvider`` instance used for the LLM fallback path.
            May be ``None`` during tests or when only the sentence-starter
            fast path is used — LLM routing will be skipped and ``blank``
            is returned if the fast path also misses.
    """

    def __init__(self, ai: "AIProvider | None" = None) -> None:
        self._ai = ai
        self._templates = _load_all_templates()
        logger.debug(
            "RoutingAgent: loaded %d templates", len(self._templates)
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def route(
        self,
        text: str,
        template_hint: str | None = None,
    ) -> RoutingDecision:
        """Return a :class:`RoutingDecision` for *text*.

        Steps:
        1. If *template_hint* is provided and matches a known template, accept
           it with confidence 1.0 (no LLM call, no starter check).
        2. Check ``sentence_starters`` for all templates (fast path, no LLM).
        3. Fall back to LLM classification via ``prompts/routing.md``.
        4. If confidence < 0.6, override template to ``blank``.

        Args:
            text:          Raw content to classify.
            template_hint: Optional caller-supplied template shortcut.

        Returns:
            :class:`RoutingDecision` with ``template``, ``note_type``,
            ``confidence``, ``fast_path``, and ``rationale``.
        """
        from monocle.telemetry import span

        async with span("agent.route", fast_path=False):
            # ----------------------------------------------------------
            # 1. Explicit template hint (user override / MCP caller)
            # ----------------------------------------------------------
            if template_hint:
                normalised = template_hint.lower().replace(" ", "_").replace("-", "_")
                # Check if it matches a valid template name
                for tmpl in self._templates:
                    if tmpl.get("template") == normalised or tmpl.get("note_type") == normalised:
                        note_type = tmpl.get("note_type", "other")
                        logger.debug(
                            "[AGENT] Routing via template_hint=%s → %s",
                            template_hint,
                            normalised,
                        )
                        return RoutingDecision(
                            template=tmpl["template"],
                            note_type=note_type,  # type: ignore[arg-type]
                            confidence=1.0,
                            fast_path=True,
                            rationale=f"Explicit template hint: '{template_hint}'",
                        )

            # ----------------------------------------------------------
            # 2. Sentence-starter fast path
            # ----------------------------------------------------------
            text_lower = text.lower().lstrip()
            for tmpl in self._templates:
                starters: list[str] = tmpl.get("sentence_starters") or []
                for starter in starters:
                    if starter and text_lower.startswith(starter.lower()):
                        note_type = tmpl.get("note_type", "other")
                        logger.debug(
                            "[AGENT] Routing via sentence starter '%s' → template=%s",
                            starter,
                            tmpl["template"],
                        )
                        return RoutingDecision(
                            template=tmpl["template"],
                            note_type=note_type,  # type: ignore[arg-type]
                            confidence=0.9,
                            fast_path=True,
                            rationale=f"Sentence starter matched: '{starter}'",
                        )

            # ----------------------------------------------------------
            # 3. LLM fallback
            # ----------------------------------------------------------
            if self._ai is None:
                logger.debug(
                    "[AGENT] No AIProvider configured — defaulting to blank template"
                )
                return RoutingDecision(
                    template="blank",
                    note_type="other",
                    confidence=0.0,
                    fast_path=False,
                    rationale="No AIProvider — sentence starters did not match",
                )

            return await self._llm_route(text)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _llm_route(self, text: str) -> RoutingDecision:
        """Call the LLM and parse its classification response."""
        from monocle.prompts import load_prompt

        prompt_body = load_prompt("routing")
        if "{{content}}" in prompt_body:
            user_content = prompt_body.replace("{{content}}", text)
            messages = [{"role": "user", "content": user_content}]
        else:
            messages = [
                {"role": "system", "content": prompt_body},
                {"role": "user", "content": text},
            ]

        try:
            raw = await self._ai.chat(messages, stream=False)  # type: ignore[union-attr]
            if not isinstance(raw, str):
                raw = "".join([chunk async for chunk in raw])  # type: ignore[arg-type]

            data = _parse_routing_response(raw)
            template = str(data.get("template", "blank")).lower()
            confidence = float(data.get("confidence", 0.5))
            rationale = str(data.get("rationale", ""))

            # Validate template against known set — reject hallucinated names.
            if template not in _TEMPLATE_NOTE_TYPES:
                logger.debug(
                    "[AGENT] LLM returned unknown template '%s', overriding to blank",
                    template,
                )
                template = "blank"
                confidence = 0.0

            # Enforce minimum confidence → blank template
            if confidence < 0.6:
                logger.debug(
                    "[AGENT] LLM confidence %.2f < 0.6, overriding template to blank",
                    confidence,
                )
                template = "blank"
                note_type: str = "other"
            else:
                note_type = _TEMPLATE_NOTE_TYPES.get(template, "other")

            logger.info(
                "[AGENT] LLM routing: template=%s confidence=%.2f",
                template,
                confidence,
            )
            return RoutingDecision(
                template=template,
                note_type=note_type,  # type: ignore[arg-type]
                confidence=confidence,
                fast_path=False,
                rationale=rationale,
            )

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[AGENT] LLM routing failed (%s) — falling back to blank",
                exc,
            )
            return RoutingDecision(
                template="blank",
                note_type="other",
                confidence=0.0,
                fast_path=False,
                rationale=f"LLM routing error: {exc}",
            )
