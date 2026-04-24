"""monocle/services/references.py — Canonical create_reference_from_url service."""
from __future__ import annotations

import asyncio
import contextlib
import html
import json
import logging
import re
import socket
import time
from typing import TYPE_CHECKING

from monocle.telemetry import span

if TYPE_CHECKING:
    from monocle.ai.base import AIProvider
    from monocle.models import Note
    from monocle.vault import VaultLayer
    from monocle.watcher import ReindexQueue

logger = logging.getLogger(__name__)

_MAX_FETCH_BYTES = 500_000  # 500 KB — cap before HTML stripping
_MAX_TEXT_CHARS = 20_000    # chars fed to the LLM summariser
_MAX_BODY_LENGTH = 50_000
_MAX_REDIRECTS = 5
_DEFAULT_URL_SUMMARISE_TIMEOUT_S = 120.0
_FALLBACK_SUMMARY_CHARS = 1_200
_FALLBACK_EXCERPT_CHARS = 4_000
_FALLBACK_BULLETS = 4

_URL_SUMMARISE_PROMPT = """\
You are a knowledge assistant. Summarise the following web page content into a concise Markdown reference note.

Instructions:
- Write 3–6 paragraphs covering the key ideas, arguments, and takeaways.
- Use a short `## Summary` section at the top, then `## Key Points` as a bullet list.
- Preserve any code examples, commands, or structured data verbatim in fenced code blocks.
- Do NOT reproduce boilerplate navigation text, cookie banners, or unrelated sidebar content.
- After the body, output a JSON block fenced with ```json containing:
  {{"title": "<short descriptive title>", "tags": ["tag1", "tag2"], "domain": "<work|personal|technology|...>"}}

Web page URL: {url}

Content:
{content}
"""


def _truncate_text(text: str, max_chars: int) -> str:
    """Return *text* capped to *max_chars* with a plain ASCII suffix."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _fallback_reference_title(url: str) -> str:
    """Generate a readable title when AI summarisation times out."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.netloc or url
    path_tail = parsed.path.strip("/").rsplit("/", 1)[-1] if parsed.path else ""
    if not path_tail:
        return host
    path_tail = re.sub(r"\.[A-Za-z0-9]{1,6}$", "", path_tail)
    path_tail = re.sub(r"[-_]+", " ", path_tail).strip()
    if not path_tail:
        return host
    return f"{host} / {path_tail}"


def _build_timeout_fallback_response(url: str, page_text: str, timeout_s: float) -> str:
    """Build a deterministic fallback response when AI summarisation times out."""
    timeout_label = f"{timeout_s:g}"
    sentences = [
        sentence.strip(" -")
        for sentence in re.split(r"(?<=[.!?])\s+", page_text)
        if sentence.strip()
    ]
    if not sentences:
        sentences = ["No extractable page text was available."]

    summary = _truncate_text(" ".join(sentences[:3]), _FALLBACK_SUMMARY_CHARS)
    key_points: list[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        candidate = _truncate_text(sentence, 220)
        if len(candidate) < 30:
            continue
        lowered = candidate.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        key_points.append(candidate)
        if len(key_points) >= _FALLBACK_BULLETS:
            break
    if not key_points:
        key_points = [_truncate_text(sentences[0], 220)]

    excerpt = _truncate_text(page_text, _FALLBACK_EXCERPT_CHARS)
    body_lines = [
        "## Summary",
        summary,
        "",
        "## Key Points",
        *[f"- {point}" for point in key_points],
        "",
        "## Extracted Excerpt",
        f"_AI summarization timed out after {timeout_label}s. This fallback note preserves the extracted page text for later review._",
        "",
        "```text",
        excerpt,
        "```",
        "",
        "```json",
        json.dumps({
            "title": _fallback_reference_title(url),
            "tags": ["fallback-summary"],
            "domain": "personal",
        }),
        "```",
    ]
    return "\n".join(body_lines)


def _strip_html(raw_html: str) -> str:
    """Remove HTML tags and decode entities, returning plain text."""
    # Remove script/style/nav/header/footer/aside blocks
    _BOILERPLATE = "script|style|nav|header|footer|aside|noscript|iframe|form"
    text = re.sub(
        rf"<({_BOILERPLATE})[^>]*>.*?</\1>", " ", raw_html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Remove all remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode HTML entities
    text = html.unescape(text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_private_ip(address: str) -> bool:
    """Return True when *address* is loopback/private/link-local/reserved."""
    import ipaddress

    try:
        addr = ipaddress.ip_address(address)
    except ValueError:
        return False

    return (
        addr.is_loopback
        or addr.is_private
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
    )


async def _resolve_host_ips(hostname: str) -> set[str]:
    """Resolve *hostname* and return all IP addresses the resolver sees."""
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, hostname, None)
    except socket.gaierror:
        return set()

    resolved: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        if sockaddr:
            resolved.add(sockaddr[0])
    return resolved


async def _is_private_url(hostname: str | None) -> bool:
    """Check literal and DNS-resolved hosts for private/loopback targets."""
    if not hostname:
        return False

    host = hostname.strip().rstrip(".")
    if host.lower() == "localhost":
        return True
    if _is_private_ip(host):
        return True

    resolved_ips = await _resolve_host_ips(host)
    return any(_is_private_ip(address) for address in resolved_ips)


async def fetch_url_text(url: str) -> str:
    """Fetch *url* via httpx and return stripped plain text.

    Raises:
        ValueError: For disallowed URL schemes or SSRF-vulnerable hosts.
        RuntimeError: For network or HTTP errors.
    """
    from urllib.parse import urljoin, urlparse

    try:
        import httpx

        async with httpx.AsyncClient(follow_redirects=False, timeout=15.0) as client:
            current_url = url
            for _ in range(_MAX_REDIRECTS + 1):
                parsed = urlparse(current_url)
                if parsed.scheme not in ("http", "https"):
                    raise ValueError(f"Only http/https URLs are supported, got: {parsed.scheme!r}")

                if await _is_private_url(parsed.hostname):
                    raise ValueError(
                        f"URL hostname {parsed.hostname!r} is not allowed (private IP, loopback, or link-local)"
                    )

                resp = await client.get(
                    current_url,
                    headers={"User-Agent": "Monocle-Reference-Bot/1.0"},
                )
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise RuntimeError(f"Redirect response missing Location header for {current_url}")
                    current_url = urljoin(current_url, location)
                    continue

                resp.raise_for_status()
                raw = resp.content[:_MAX_FETCH_BYTES].decode("utf-8", errors="replace")
                break
            else:
                raise RuntimeError(f"Too many redirects fetching {url}")
    except ValueError:
        raise
    except Exception as exc:
        if hasattr(exc, "response"):
            raise RuntimeError(f"HTTP {exc.response.status_code} fetching {url}") from exc  # type: ignore[union-attr]
        raise RuntimeError(f"Network error fetching {url}: {exc}") from exc

    return _strip_html(raw)[:_MAX_TEXT_CHARS]


# Canonical tag normaliser — shared across MCP, agent tools, and services.
from monocle.services.tags import normalize_tags as _normalize_tags


async def create_reference_from_url(
    vault: "VaultLayer",
    ai: "AIProvider",
    reindex_queue: "ReindexQueue | None",
    url: str,
    extra_context: str | None = None,
    *,
    summarize_timeout_s: float | None = None,
) -> "Note":
    """Fetch a URL, AI-summarise it, and create a reference note.

    Args:
        vault: The vault layer instance.
        ai: AI provider for summarisation.
        reindex_queue: Optional reindex queue for embedding updates.
        url: The ``http://`` or ``https://`` URL to fetch.
        extra_context: Optional additional focus/instructions for the summariser.

    Returns:
        The newly created reference ``Note``.

    Raises:
        RuntimeError: If *ai* is ``None`` or if fetching / summarisation fails.
        ValueError: If *url* has a disallowed scheme.
    """
    timeout_s = summarize_timeout_s or _DEFAULT_URL_SUMMARISE_TIMEOUT_S
    async with span("tool.create_reference_from_url", tool_name="create_reference_from_url", url=url) as trace_span:
        fetch_started = time.monotonic()
        async with span("reference.fetch_url", url=url):
            page_text = await fetch_url_text(url)
        fetch_ms = (time.monotonic() - fetch_started) * 1000

        # 2. Build summarisation prompt
        prompt_content = _URL_SUMMARISE_PROMPT.format(url=url, content=page_text)
        if extra_context:
            prompt_content += f"\n\nAdditional instructions: {extra_context}"

        # 3. Ask AI to summarise
        summarize_started = time.monotonic()
        used_fallback = False
        async with span("reference.summarize_url", url=url, content_chars=len(page_text)):
            try:
                async with asyncio.timeout(timeout_s):
                    raw_response = await ai.chat(
                        [{"role": "user", "content": prompt_content}],
                        stream=False,
                    )
                    if not isinstance(raw_response, str):
                        # Consume the async generator if the provider returned one.
                        parts: list[str] = []
                        async for chunk in raw_response:
                            parts.append(chunk)
                        raw_response = "".join(parts)
            except TimeoutError:
                used_fallback = True
                raw_response = _build_timeout_fallback_response(url, page_text, timeout_s)
                logger.warning(
                    "[REF] URL summarization timed out after %ss; using fallback summary for %s",
                    f"{timeout_s:g}",
                    url,
                )
        summarize_ms = (time.monotonic() - summarize_started) * 1000

        # 4. Extract the embedded JSON metadata block (last ```json ... ``` fence)
        json_matches = list(re.finditer(r"```json\s*(\{.*?\})\s*```", raw_response, re.DOTALL))
        if json_matches:
            json_match = json_matches[-1]
            try:
                meta = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                meta = {}
            body = raw_response[:json_match.start()].strip()
        else:
            meta = {}
            body = raw_response.strip()

        title = meta.get("title") or url
        tags = _normalize_tags(meta.get("tags")) or []
        domain = meta.get("domain") or "personal"

        # Prepend source URL to body
        body = f"> Source: {url}\n\n{body}"
        if len(body) > _MAX_BODY_LENGTH:
            body = body[:_MAX_BODY_LENGTH]

        # 5. Create the note
        from monocle.models import NoteMetadata

        metadata = NoteMetadata(
            type="reference",
            domain=domain,
            tags=["web-reference"] + tags,
            review_status="pending",
            source="web",
        )
        write_started = time.monotonic()
        async with span("reference.write_note", url=url, title=title):
            note = await asyncio.to_thread(
                vault.create_from_template,
                "reference",
                {"title": title, **metadata.model_dump(exclude={"template"}, exclude_none=True)},
                body,
            )
            await asyncio.to_thread(vault.write_note, note.file_path, note)
        write_ms = (time.monotonic() - write_started) * 1000
        if reindex_queue is not None:
            reindex_queue.push(note.file_path)
        if trace_span is not None:
            with contextlib.suppress(Exception):
                trace_span.set_attribute("reference.summarize_fallback", used_fallback)
                trace_span.set_attribute("reference.summarize_timeout_s", timeout_s)
                trace_span.set_attribute("reference.fetch_ms", round(fetch_ms, 1))
                trace_span.set_attribute("reference.summarize_ms", round(summarize_ms, 1))
                trace_span.set_attribute("reference.write_ms", round(write_ms, 1))
                trace_span.set_attribute("reference.content_chars", len(page_text))
                trace_span.set_attribute("reference.response_chars", len(raw_response))
                trace_span.set_attribute("reference.file_path", note.file_path)
                trace_span.set_attribute("reference.total_ms", round(fetch_ms + summarize_ms + write_ms, 1))
        logger.info(
            "[REF] create_reference_from_url complete url=%s fetch=%.1fms summarize=%.1fms write=%.1fms file=%s",
            url,
            fetch_ms,
            summarize_ms,
            write_ms,
            note.file_path,
        )
        return note
