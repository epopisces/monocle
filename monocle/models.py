"""
monocle/models.py — All shared Pydantic v2 models.

These are the canonical data-transfer types used across routers, the ingest
pipeline, vault layer, index layer, and agent layer.  No business logic here.
"""
from __future__ import annotations

from datetime import datetime
import base64 as _b64
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, BeforeValidator, Field

def _coerce_audio_bytes(v: Any) -> bytes | None:
    """Accept raw bytes (pass-through) or a base64-encoded str (decode it)."""
    if v is None:
        return None
    if isinstance(v, (bytes, bytearray)):
        return bytes(v)
    if isinstance(v, str):
        return _b64.b64decode(v)
    raise ValueError(f"audio_bytes must be bytes or a base64 string, got {type(v).__name__}")


AudioBytesField = Annotated[bytes | None, BeforeValidator(_coerce_audio_bytes)]


T = TypeVar("T")

# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

NoteSource = Literal["web", "voice", "teams", "mcp", "import"]
ReviewStatus = Literal["pending", "approved"]
ApprovalMode = Literal["auto", "manual"]

NOTE_TYPES = Literal[
    "person_note",
    "decision",
    "idea",
    "observation",
    "reference",
    "meeting_note",
    "project",
    "action_item",
    "weekly_summary",
    "other",
]


# ---------------------------------------------------------------------------
# Link / graph types
# ---------------------------------------------------------------------------


class LinkRef(BaseModel):
    """A structured link from a note's `links:` frontmatter field."""

    target: str
    relation: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    degree: int | None = None  # BFS distance from focus; None in full-vault mode
    weight: int = 1


class GraphEdge(BaseModel):
    source: str
    target: str
    edge_type: Literal["structured", "wikilink", "co-mention"] = "wikilink"
    relation: str | None = None
    weight: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphData(BaseModel):
    focus: str | None = None
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Note models
# ---------------------------------------------------------------------------


class NoteMetadata(BaseModel):
    """Parsed frontmatter of a note as written/read by the ingest pipeline."""

    type: NOTE_TYPES = "other"
    template: str = "blank"
    domain: str = "personal"
    people: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    source: NoteSource = "web"
    action_items: list[str] = Field(default_factory=list)
    created: datetime | None = None
    updated: datetime | None = None
    confidence: float = 1.0
    confidence_rationale: str | None = None
    review_status: ReviewStatus = "approved"
    approved_by: str | None = None
    approved_at: datetime | None = None
    approval_mode: ApprovalMode | None = None
    links: list[LinkRef] = Field(default_factory=list)
    # Optional org field for multi-employer support
    org: str | None = None

    model_config = {"extra": "allow"}  # allow arbitrary frontmatter fields


class NoteRef(BaseModel):
    """Lightweight reference to a note (used in listings and search results)."""

    file_path: str
    title: str
    type: NOTE_TYPES = "other"
    domain: str = "personal"
    tags: list[str] = Field(default_factory=list)
    created: datetime | None = None
    updated: datetime | None = None
    confidence: float = 1.0
    review_status: ReviewStatus = "approved"


class Note(BaseModel):
    """Full note contents including frontmatter metadata and Markdown body."""

    file_path: str
    title: str
    body: str
    metadata: NoteMetadata = Field(default_factory=NoteMetadata)
    mtime: float | None = None  # filesystem mtime for optimistic concurrency


class NoteChunk(BaseModel):
    """A single embedding chunk derived from a note."""

    chunk_id: str  # "{file_path}::{chunk_index}"
    file_path: str
    chunk_index: int
    text: str
    embedding: list[float] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    offset: int = 0
    limit: int = 50


# ---------------------------------------------------------------------------
# Ingest models
# ---------------------------------------------------------------------------


class IngestRequest(BaseModel):
    content: str | None = None
    content_type: str = "text/plain"
    source: NoteSource = "web"
    template_hint: str | None = None
    audio_bytes: AudioBytesField = Field(default=None, exclude=True)
    audio_mime_type: str | None = None
    allow_duplicate: bool = False  # FR-ING-11: advisory duplicate-detection flow


class IngestConfidence(BaseModel):
    """Deterministic confidence score for an ingested note (no LLM call)."""

    score: float  # 0.0–1.0
    template_match: float
    metadata_coverage: float
    tag_plausibility: float
    entity_match: float
    rationale: str | None = None
    # Advisory duplicate-detection fields (FR-ING-11)
    similar_note_detected: bool = False
    similar_note_path: str | None = None


# ---------------------------------------------------------------------------
# Index models
# ---------------------------------------------------------------------------


class ScoredChunk(BaseModel):
    chunk_id: str
    file_path: str
    score: float
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class IndexStats(BaseModel):
    total_chunks: int = 0
    total_files: int = 0
    collection_name: str = ""
    backend: str = "chroma"


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class BrainStats(BaseModel):
    total_notes: int = 0
    total_chunks: int = 0
    notes_by_type: dict[str, int] = Field(default_factory=dict)
    notes_by_domain: dict[str, int] = Field(default_factory=dict)
    pending_review: int = 0
    failed_ingests: int = 0
    index: IndexStats = Field(default_factory=IndexStats)
    # Latency percentiles per operation type (sourced from OTel histogram snapshots)
    # Keys: "embed", "chat", "transcribe", "ingest", "search"
    latency_p50_ms: dict[str, float] = Field(default_factory=dict)
    latency_p95_ms: dict[str, float] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Ingest response
# ---------------------------------------------------------------------------


class IngestResponse(BaseModel):
    """Response body for POST /api/ingest."""

    note: Note
    confidence: IngestConfidence


# ---------------------------------------------------------------------------
# Agent / routing models
# ---------------------------------------------------------------------------


class RoutingDecision(BaseModel):
    template: str  # e.g. "person", "decision"
    note_type: NOTE_TYPES = "other"
    confidence: float = 0.0
    fast_path: bool = False  # True when sentence_starters matched (no LLM used)
    rationale: str | None = None
