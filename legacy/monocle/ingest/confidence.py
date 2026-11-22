"""
monocle/ingest/confidence.py — Deterministic confidence scoring for ingested notes.

Computes a weighted confidence score from four observable signals.  Zero LLM
calls are made — the body embedding produced during step 6 of the ingest
pipeline is passed in so no additional AI round-trip is needed.

Formula:
    score = 0.35 * template_match
          + 0.30 * metadata_coverage
          + 0.20 * tag_plausibility
          + 0.15 * entity_match

Weights are read from ``settings.review.confidence_weights`` so they are
customisable per deployment without touching code.

Auto-approval logic (written to note frontmatter by the caller):
    - ``auto_approve_threshold_pct == 0`` → always pending
    - ``score * 100 >= auto_approve_threshold_pct`` → approved (auto)
    - otherwise → pending
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from monocle.models import IngestConfidence

if TYPE_CHECKING:
    from monocle.config import Settings
    from monocle.models import Note
    from monocle.vault import VaultLayer

logger = logging.getLogger(__name__)

#endregion

# ---------------------------------------------------------------------------
#region #*   Template schema cache (re-uses _load_template_schema from vault layer)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=64)
def _load_template_schema(template_name: str) -> dict[str, Any]:
    """Load a YAML template schema by name (blank fallback)."""
    template_dir = Path(__file__).parent.parent / "vault" / "templates"
    yaml_file = template_dir / f"{template_name}.yaml"
    if not yaml_file.exists():
        yaml_file = template_dir / "blank.yaml"
    try:
        with open(yaml_file, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("confidence: could not load template schema %s: %s", template_name, exc)
        return {}


#endregion

# ---------------------------------------------------------------------------
#region #*   Public API
# ---------------------------------------------------------------------------


def score_confidence(
    note: "Note",
    routing_confidence: float,
    body_embedding: "list[float]",
    vault: "VaultLayer",
    settings: "Settings",
) -> IngestConfidence:
    """Compute a deterministic confidence score for *note*.

    Components:
    1. **template_match** (weight 0.35) — routing agent confidence (passed in
       directly from the ``RoutingDecision``).
    2. **metadata_coverage** (weight 0.30) — fraction of required template
       fields that have non-empty values in the note.
    3. **tag_plausibility** (weight 0.20) — fraction of tags that appear as
       words/substrings in the note body (case-insensitive).  1.0 when no tags.
    4. **entity_match** (weight 0.15) — fraction of named people in the note
       that resolve to an existing vault note.  1.0 when no people listed.

    Args:
        note:               Fully constructed note (body + metadata populated).
        routing_confidence: Confidence from the routing step (0.0–1.0).
        body_embedding:     First-chunk embedding from step 6 (not used in the
                            formula itself but kept as a parameter for future
                            semantic tag scoring extensions).
        vault:              VaultLayer used for entity resolution.
        settings:           Settings object supplying ``review.confidence_weights``.

    Returns:
        :class:`~monocle.models.IngestConfidence` with all component scores,
        the weighted total, and a human-readable ``rationale`` string.
    """
    weights = settings.review.confidence_weights

    # ------------------------------------------------------------------
    # 1. Template match
    # ------------------------------------------------------------------
    template_match = min(1.0, max(0.0, routing_confidence))

    # ------------------------------------------------------------------
    # 2. Metadata coverage
    # ------------------------------------------------------------------
    template_name = (note.metadata.template or "blank").lower()
    schema = _load_template_schema(template_name)
    required_fields: list[dict[str, Any]] = [
        f for f in (schema.get("fields") or []) if f.get("required", False)
    ]

    if not required_fields:
        metadata_coverage = 1.0
    else:
        fm = note.metadata.model_dump()
        populated = 0
        for field_spec in required_fields:
            field_name = field_spec.get("name", "")
            if field_name == "title":
                # title lives on Note, not NoteMetadata
                val = note.title
            else:
                val = fm.get(field_name)
            if val not in (None, "", [], {}):
                populated += 1
        metadata_coverage = min(1.0, populated / len(required_fields))

    # ------------------------------------------------------------------
    # 3. Tag plausibility (text-based, deterministic — no AI call)
    # ------------------------------------------------------------------
    tags: list[str] = list(note.metadata.tags or [])
    if not tags:
        tag_plausibility = 1.0
    else:
        body_lower = (note.body or "").lower()
        matched = 0
        for tag in tags:
            # Check both hyphenated form (e.g. "machine-learning") and
            # space-separated form (e.g. "machine learning") in the body.
            tag_lower = tag.lower()
            tag_spaced = tag_lower.replace("-", " ")
            if tag_lower in body_lower or tag_spaced in body_lower:
                matched += 1
        tag_plausibility = matched / len(tags)

    # ------------------------------------------------------------------
    # 4. Entity match — people with existing vault notes
    # ------------------------------------------------------------------
    people: list[str] = list(note.metadata.people or [])
    if not people:
        entity_match = 1.0
    else:
        found = 0
        for person in people:
            try:
                if vault.resolve_wikilink(person) is not None:
                    found += 1
            except Exception:  # noqa: BLE001
                pass
        entity_match = found / max(len(people), 1)

    # ------------------------------------------------------------------
    # Weighted total
    # ------------------------------------------------------------------
    score = (
        weights.template_match * template_match
        + weights.metadata_coverage * metadata_coverage
        + weights.tag_plausibility * tag_plausibility
        + weights.entity_match * entity_match
    )
    score = min(1.0, max(0.0, score))

    rationale = (
        f"template_match={template_match:.2f} "
        f"metadata_coverage={metadata_coverage:.2f} "
        f"tag_plausibility={tag_plausibility:.2f} "
        f"entity_match={entity_match:.2f}"
    )

    logger.debug("[INGEST] Confidence score: %.3f (%s)", score, rationale)

    return IngestConfidence(
        score=score,
        template_match=template_match,
        metadata_coverage=metadata_coverage,
        tag_plausibility=tag_plausibility,
        entity_match=entity_match,
        rationale=rationale,
    )


def compute_approval_metadata(
    score: float,
    settings: "Settings",
) -> dict[str, Any]:
    """Return frontmatter fields for review_status and approval.

    Args:
        score:    Weighted confidence score (0.0–1.0).
        settings: Settings object supplying ``review.auto_approve_threshold_pct``.

    Returns:
        Dict with ``review_status``, ``confidence``, and optionally
        ``approval_mode``, ``approved_by``, ``approved_at``.
    """
    threshold = settings.review.auto_approve_threshold_pct
    updates: dict[str, Any] = {"confidence": score}

    if threshold > 0 and score * 100 >= threshold:
        updates["review_status"] = "approved"
        updates["approval_mode"] = "auto"
        updates["approved_by"] = "system:auto"
        updates["approved_at"] = datetime.now(timezone.utc).isoformat()
        logger.debug(
            "[INGEST] Auto-approved (score=%.3f, threshold=%d%%)", score, threshold
        )
    else:
        updates["review_status"] = "pending"
        logger.debug(
            "[INGEST] Note queued for review (score=%.3f, threshold=%d%%)",
            score,
            threshold,
        )

    return updates
