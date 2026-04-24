"""
monocle/models.py — All shared Pydantic v2 models.

These are the canonical data-transfer types used across routers, the ingest
pipeline, vault layer, index layer, and agent layer.  No business logic here.
"""
from __future__ import annotations

# Apply Python 3.14 compatibility patches BEFORE importing Pydantic
import monocle.compat as _compat  # noqa: F401

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

#endregion

# ---------------------------------------------------------------------------
#region #*   Primitives
# ---------------------------------------------------------------------------

NoteSource = Literal["web", "voice", "teams", "mcp", "import", "agent"]
IngestSessionOrigin = Literal["api", "chat", "inbox"]
IngestNotificationStatus = Literal["unread", "read", "dismissed"]
IngestSessionState = Literal[
    "captured",
    "queued",
    "preparing",
    "dormant_ready",
    "in_review",
    "awaiting_user",
    "proposal_ready",
    "approved_pending_execution",
    "executing",
    "completed",
    "failed",
    "dismissed",
]
SourceRecordKind = Literal["text", "audio", "file", "url", "chat_text", "chat_upload"]
SourceRecordStatus = Literal[
    "captured",
    "archived",
    "queued",
    "processing",
    "ready",
    "consumed",
    "completed",
    "failed",
    "dismissed",
]
ProposedActionType = Literal["create_note", "update_note"]
ProposedActionApprovalState = Literal[
    "draft",
    "edited",
    "approved",
    "rejected",
    "executed",
    "failed",
]
ReviewStatus = Literal["pending", "approved", "rejected"]
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
    "organization",
    "other",
]


#endregion

# ---------------------------------------------------------------------------
#region #*   Link / graph types
# ---------------------------------------------------------------------------


class LinkRef(BaseModel):
    """A structured link from a note's `links:` frontmatter field."""

    target: str
    relation: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceLink(BaseModel):
    """A provenance link from a note back to an archived raw source."""

    source_id: str
    session_id: str | None = None
    source_name: str
    archive_path: str
    kind: SourceRecordKind
    mime_type: str | None = None
    captured_at: str | None = None
    author: str | None = None


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


#endregion

# ---------------------------------------------------------------------------
#region #*   Note models
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
    sources: list[SourceLink] = Field(default_factory=list)
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


class NoteHistoryEntry(BaseModel):
    timestamp: str
    title: str | None = None
    updated: datetime | None = None
    body_excerpt: str | None = None
    byte_size: int = 0


class NoteHistoryVersionResponse(BaseModel):
    timestamp: str
    note: Note


class NoteChunk(BaseModel):
    """A single embedding chunk derived from a note."""

    chunk_id: str  # "{file_path}::{chunk_index}"
    file_path: str
    chunk_index: int
    text: str
    embedding: list[float] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


#endregion

# ---------------------------------------------------------------------------
#region #*   Pagination
# ---------------------------------------------------------------------------


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    offset: int = 0
    limit: int = 50


#endregion

# ---------------------------------------------------------------------------
#region #*   Ingest models
# ---------------------------------------------------------------------------


class IngestRequest(BaseModel):
    content: str | None = None
    content_type: str = "text/plain"
    source: NoteSource = "web"
    origin: IngestSessionOrigin = "api"
    template_hint: str | None = None
    audio_bytes: AudioBytesField = Field(
        default=None,
        exclude=True,
        description="Base64-encoded audio data (WAV, MP3, FLAC, etc.). Can also be raw bytes in multipart requests.",
    )
    audio_mime_type: str | None = None
    allow_duplicate: bool = False  # FR-ING-11: advisory duplicate-detection flow
    fast_capture: bool = False


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


#endregion

# ---------------------------------------------------------------------------
#region #*   Index models
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


#endregion

# ---------------------------------------------------------------------------
#region #*   Stats
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


#endregion

# ---------------------------------------------------------------------------
#region #*   Ingest response
# ---------------------------------------------------------------------------


class IngestNotification(BaseModel):
    id: str
    kind: str
    status: IngestNotificationStatus = "unread"
    created_at: str


class IngestNotificationSummary(BaseModel):
    notification_id: str
    session_id: str
    kind: str
    status: IngestNotificationStatus
    created_at: str
    session_state: IngestSessionState
    session_title: str | None = None
    session_digest: str | None = None
    source_names: list[str] = Field(default_factory=list)
    open_questions_count: int = 0
    contradictions_count: int = 0
    proposed_actions_count: int = 0


class CountResponse(BaseModel):
    count: int


class DiffPreviewHunk(BaseModel):
    section: str | None = None
    before: str | None = None
    after: str | None = None


class DiffPreview(BaseModel):
    kind: str
    before_excerpt: str | None = None
    after_excerpt: str | None = None
    hunks: list[DiffPreviewHunk] = Field(default_factory=list)


class NoteHistoryDiffResponse(BaseModel):
    file_path: str
    base_timestamp: str
    compare_timestamp: str | None = None
    base_label: str
    compare_label: str
    diff_preview: DiffPreview


class IngestExecutionValidation(BaseModel):
    title_match: bool = False
    body_match: bool = False
    sources_attached: bool = False


class ProposedActionExecutionResult(BaseModel):
    status: Literal["succeeded", "failed", "skipped"]
    message: str | None = None
    file_path: str | None = None
    executed_at: str | None = None
    validation: IngestExecutionValidation | None = None


class IngestExecutionSummary(BaseModel):
    total_actions: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    affected_file_paths: list[str] = Field(default_factory=list)
    completed_at: str | None = None


class ProposedAction(BaseModel):
    action_id: str
    action_type: ProposedActionType
    approval_state: ProposedActionApprovalState
    target_file_path: str | None = None
    target_note_type: str | None = None
    rationale: str
    diff_preview: DiffPreview | dict[str, Any] | None = None
    proposed_content: dict[str, Any] = Field(default_factory=dict)
    execution_result: ProposedActionExecutionResult | dict[str, Any] | None = None


class SourceRecord(BaseModel):
    source_id: str
    session_id: str
    kind: SourceRecordKind
    status: SourceRecordStatus
    source_name: str
    mime_type: str | None = None
    archive_path: str
    checksum_sha256: str
    captured_at: str
    byte_size: int = 0
    provenance: dict[str, Any] = Field(default_factory=dict)


class IngestSession(BaseModel):
    session_id: str
    origin: IngestSessionOrigin
    state: IngestSessionState
    fast_capture: bool = False
    source_ids: list[str] = Field(default_factory=list)
    title: str | None = None
    digest: str | None = None
    open_questions: list[dict[str, Any]] = Field(default_factory=list)
    related_notes: list[dict[str, Any]] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    created_at: str
    updated_at: str
    prepared_at: str | None = None
    last_true_up_at: str | None = None
    execution_summary: IngestExecutionSummary | None = None


class IngestSessionDetailResponse(BaseModel):
    session: IngestSession
    sources: list[SourceRecord] = Field(default_factory=list)


class ArchivedSourceContentResponse(BaseModel):
    source: SourceRecord
    text: str
    truncated: bool = False


class IngestResponse(BaseModel):
    """Accepted ingest-session summary returned by POST /api/ingest."""

    session_id: str
    origin: IngestSessionOrigin
    state: IngestSessionState
    source_ids: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    notification: IngestNotification | None = None


class IngestTrueUpResponse(BaseModel):
    session_id: str
    job_id: str
    state: IngestSessionState
    last_true_up_at: str


class IngestOpenQuestionAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=10_000)


class ProposedActionPatchRequest(BaseModel):
    target_file_path: str | None = None
    target_note_type: NOTE_TYPES | None = None
    rationale: str | None = None
    proposed_content: dict[str, Any] | None = None

    model_config = {"extra": "forbid"}


#endregion

# ---------------------------------------------------------------------------
#region #*   Agent / routing models
# ---------------------------------------------------------------------------


class RoutingDecision(BaseModel):
    template: str  # e.g. "person", "decision"
    note_type: NOTE_TYPES = "other"
    confidence: float = 0.0
    fast_path: bool = False  # True when sentence_starters matched (no LLM used)
    rationale: str | None = None


#endregion

# ---------------------------------------------------------------------------
#region #*   Provider / model status
# ---------------------------------------------------------------------------


class ModelStatus(BaseModel):
    """Status of a single configured model role."""

    name: str
    """Model name as configured (e.g. "llama3.2", "nomic-embed-text")."""

    role: Literal["chat", "embed", "transcribe"]
    """Functional role this model serves."""

    available: bool
    """True when the model is pulled/accessible on the provider (can be used)."""

    loaded: bool
    """True when the model is currently resident in memory/GPU (ready immediately)."""


class ProviderModelsResponse(BaseModel):
    """Response for GET /api/health/models."""

    provider: str
    """Provider name: "ollama", "foundry_local", or "azure"."""

    provider_reachable: bool
    """False when the provider HTTP endpoint could not be contacted."""

    models: list[ModelStatus]
    """Status of each configured model role."""
