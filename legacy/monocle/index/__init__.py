"""
monocle/index/__init__.py — IndexLayer factory.

Usage::

    from monocle.index import get_index
    index = get_index(settings)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

# Re-export key symbols so callers only need to import from monocle.index
from monocle.index.base import DimensionMismatch, IndexLayer  # noqa: F401

if TYPE_CHECKING:
    from monocle.config import Settings


def get_index(settings: "Settings") -> IndexLayer:
    """Construct and return the configured :class:`IndexLayer` implementation.

    Raises
    ------
    NotImplementedError
        If ``settings.index.backend`` names an unsupported backend.
    DimensionMismatch
        If a ChromaDB collection already exists with a different
        ``embed_dimensions`` than the current config.
    """
    if settings.index.backend == "chroma":
        from monocle.index.chroma import ChromaIndex

        return ChromaIndex(settings)

    raise NotImplementedError(f"Unsupported index backend: {settings.index.backend!r}")
