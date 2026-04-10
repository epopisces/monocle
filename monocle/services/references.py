"""monocle/services/references.py — Canonical create_reference_from_url service."""
from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import socket
from typing import TYPE_CHECKING

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
    # 1. Fetch and strip the page
    page_text = await fetch_url_text(url)

    # 2. Build summarisation prompt
    prompt_content = _URL_SUMMARISE_PROMPT.format(url=url, content=page_text)
    if extra_context:
        prompt_content += f"\n\nAdditional instructions: {extra_context}"

    # 3. Ask AI to summarise
    raw_response = await ai.chat(
        [{"role": "user", "content": prompt_content}],
        stream=False,
    )
    if not isinstance(raw_response, str):
        # Consume the async generator if the provider returned one
        parts: list[str] = []
        async for chunk in raw_response:
            parts.append(chunk)
        raw_response = "".join(parts)

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
    note = await asyncio.to_thread(
        vault.create_from_template,
        "reference",
        {"title": title, **metadata.model_dump(exclude={"template"}, exclude_none=True)},
        body,
    )
    await asyncio.to_thread(vault.write_note, note.file_path, note)
    if reindex_queue is not None:
        reindex_queue.push(note.file_path)
    return note
