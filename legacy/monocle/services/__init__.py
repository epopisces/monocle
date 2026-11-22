"""
monocle/services/ — Canonical shared service layer for Monocle data operations.

All Monocle business logic for vault data operations lives here.
Both MCP tools and chat agent tools are thin wrappers that delegate to
these service functions.

See docs/tool-contracts.md for the canonical contract definitions.

Modules:
    search      — search_vault()
    notes       — read_note(), create_note(), update_note()
    graph       — get_graph()
    references  — create_reference_from_url()
    ingest      — capture_thought(), capture_thought_session()
    ingest_workflow — consolidated prepare/review/execute orchestration
    tags        — normalize_tags() shared utility
"""
