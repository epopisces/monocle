"""
monocle/ingest/chunker.py — Text chunking using tiktoken.

Splits a plain-text string into overlapping token windows suitable for
embedding and storage in the vector index.

Configuration defaults (also reflected in IndexConfig):
    chunk_size   = 512 tokens
    overlap      = 64  tokens
    encoding     = cl100k_base  (used by text-embedding-ada-002 and GPT-4)
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Module-level encoder cache populated on first chunk_text() call.
# Avoids re-constructing the tiktoken Encoding on every call while keeping
# the import lazy (tiktoken is not required at module load time).
_cl100k_enc = None  # type: ignore[assignment]  # tiktoken.Encoding | None


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[str]:
    """Split *text* into overlapping token-window chunks.

    Parameters
    ----------
    text:
        The raw text to chunk.  Leading/trailing whitespace is preserved so
        that reconstructed text round-trips cleanly.
    chunk_size:
        Maximum tokens per chunk.
    overlap:
        Number of tokens from the end of the previous chunk to repeat at the
        start of the next chunk.  Must be < *chunk_size*.

    Returns
    -------
    list[str]
        Ordered list of decoded text chunks.  Empty text returns ``[]``.
        Text shorter than *chunk_size* tokens returns a single-element list.
    """
    if not text or not text.strip():
        return []

    if overlap >= chunk_size:
        raise ValueError(
            f"overlap ({overlap}) must be less than chunk_size ({chunk_size})"
        )

    global _cl100k_enc
    if _cl100k_enc is None:
        try:
            import tiktoken  # lazy import — not needed at module load time
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "tiktoken is required for text chunking. "
                "Install it with: uv add tiktoken"
            ) from exc
        _cl100k_enc = tiktoken.get_encoding("cl100k_base")

    enc = _cl100k_enc
    tokens = enc.encode(text)

    if not tokens:
        return []

    chunks: list[str] = []
    start = 0

    while start < len(tokens):
        end = start + chunk_size
        chunk_tokens = tokens[start:end]
        chunks.append(enc.decode(chunk_tokens))

        if end >= len(tokens):
            break

        start = end - overlap

    logger.debug(
        "chunk_text: %d tokens → %d chunk(s) (size=%d, overlap=%d)",
        len(tokens),
        len(chunks),
        chunk_size,
        overlap,
    )
    return chunks
