---
type: plan
project: monocle
last-updated: 2026-04-07
status: proposed
---

# MCP-First Chat Refactor Plan

## Goal

Reduce the current split-brain architecture by making the Monocle MCP server the canonical tool surface for Monocle-owned data operations, while keeping the chat API as the orchestration and streaming UX layer.

This plan does **not** propose replacing the chat API with direct browser-to-MCP traffic. Instead, it proposes that chat becomes an internal client of the same canonical Monocle tool plane used by external MCP clients.

## Problem Statement

Monocle currently maintains two overlapping tool surfaces for the same domain:

1. Agent tools used by the chat endpoint.
2. MCP tools exposed to external clients.

This causes predictable problems:

1. Duplicate business logic for search, read, create, update, graph, and URL-reference workflows.
2. Contract drift between agent tools and MCP tools.
3. Duplicate testing effort for the same underlying behavior.
4. More places where semantics can diverge, especially around validation, note metadata, review status, and reindex behavior.

The April 2026 work already shows this drift pressure: tool renames, input/output alignment work, and separate URL summarization implementations with near-identical behavior.

## Recommended Direction

Adopt an **MCP-first internal architecture**:

1. MCP becomes the authoritative contract for Monocle-owned operations.
2. Chat continues to own session orchestration, token streaming, tool-call UX, URL prefetch policy, and telemetry.
3. Chat invokes Monocle operations through an internal MCP-compatible layer rather than maintaining a separate first-class tool implementation for the same domain.
4. Lightweight non-MCP agent logic remains allowed for:
   - routing and planning,
   - pre/post-processing of user intent,
   - third-party MCP server usage,
   - purely local orchestration that does not duplicate Monocle data operations.

## Non-Goals

This refactor should **not**:

1. Turn the browser into a direct MCP client.
2. Remove the `/api/chat` SSE endpoint.
3. Force external MCP transport concerns into the frontend.
4. Rewrite the entire chat stack in one step.
5. Require network-loopback MCP calls if an in-process adapter can provide the same contract more cheaply.

## Target Architecture

### Canonical responsibility split

1. **MCP tool plane**
   - Owns Monocle data operations.
   - Defines canonical tool schemas and return contracts.
   - Is used by both external MCP clients and internal chat orchestration.

2. **Chat orchestration plane**
   - Owns `/api/chat` request handling.
   - Owns SSE framing: `token`, `tool_call`, `tool_error`, `note_created`, `done`.
   - Owns chat-only behaviors such as URL pill opt-in flow, prefetch batching, session handling, and model interaction policy.
   - Delegates Monocle operations to the canonical MCP tool plane.

3. **Third-party tool plane**
   - Optional external MCP servers or lightweight local agent-only helpers.
   - Used when functionality is not Monocle-owned.

### Practical interpretation

The chat agent should still exist, but it should stop being the place where Monocle business operations are primarily implemented.

Instead:

1. The agent plans.
2. The agent calls canonical Monocle tools.
3. Those canonical tools are the same ones exposed through MCP.
4. Chat remains a server-side composition layer over that tool plane.

## Preferred Implementation Strategy

There are two viable implementation patterns.

### Option A: Shared service layer under both MCP and chat

Create a service layer such as:

1. `monocle/services/notes.py`
2. `monocle/services/search.py`
3. `monocle/services/graph.py`
4. `monocle/services/references.py`
5. `monocle/services/ingest.py`

Then:

1. MCP tools become thin schema/transport wrappers over those services.
2. Chat tool calls also become thin wrappers over those same services.

Pros:

1. Lowest migration risk.
2. Preserves existing agent framework integration.
3. Removes duplicate business logic without requiring an MCP client adapter first.

Cons:

1. Still leaves two tool-definition layers.
2. Canonicality is implemented by convention, not by a single invocation path.

### Option B: In-process MCP client/adapter for chat

Keep MCP tool definitions as the only Monocle tool definitions, and let chat invoke them through an internal adapter.

That adapter should:

1. Call the same underlying MCP tool implementations in-process.
2. Avoid HTTP loopback and auth overhead.
3. Translate agent framework tool calls into MCP tool invocations.
4. Normalize result handling so chat SSE events remain unchanged.

Pros:

1. Strongest architectural clarity.
2. True single tool plane for Monocle-owned operations.
3. Eliminates contract drift almost completely.

Cons:

1. Slightly higher initial integration complexity.
2. Requires careful mapping between agent-framework tool schemas and MCP tool schemas.

### Recommendation

Use a staged approach:

1. Start with **Option A** to eliminate business-logic duplication safely.
2. Move to **Option B** once service boundaries and result contracts are stable.

This gives immediate payoff without forcing a risky one-shot rewrite.

## Milestones

### M29: Contract Freeze & Canonical Tool Schema

**Goal:** Establish a single source-of-truth contract for all Monocle-owned data operations before any code moves.

**Deliverables:**

- [x] **D1:** Canonical tool contract table added to this document (or a dedicated `docs/tool-contracts.md`), defining for each operation: canonical name, input schema, output schema, side effects, required app state, review/reindex semantics, and chat-only decorations (if any)
- [x] **D2:** Explicit mapping table from current agent-tool names (`VaultTools`) to canonical MCP names
- [x] **D3:** Decision documented: `fetch_and_summarize_url` is fully replaced by `create_reference_from_url` + chat-only prefetch orchestration, OR kept as a chat-only alias — with rationale
- [x] **D4:** Canonical operation set finalized (initial: `search_vault`, `read_note`, `capture_thought`, `create_note`, `update_note`, `get_graph`, `create_reference_from_url`)

**Acceptance criteria:**

1. Contract table exists and covers all 7 canonical operations.
2. Every current agent tool and MCP tool is mapped to exactly one canonical operation or explicitly marked "chat-only / not canonical."
3. No code changes required — this milestone is documentation and design only.

**Test command:** N/A (documentation milestone)

---

### M30: Shared Service Layer Extraction

**Goal:** Move all Monocle business logic out of both tool layers into shared service functions under `monocle/services/`.

**Deliverables:**

- [x] **D1:** Create `monocle/services/__init__.py`
- [x] **D2:** Create `monocle/services/search.py` — `search_vault(...)` extracted from MCP/agent tool implementations
- [x] **D3:** Create `monocle/services/notes.py` — `read_note(...)`, `create_note(...)`, `update_note(...)` extracted
- [x] **D4:** Create `monocle/services/graph.py` — `get_graph(...)` extracted
- [x] **D5:** Create `monocle/services/references.py` — `create_reference_from_url(...)` extracted
- [x] **D6:** Create `monocle/services/ingest.py` — `capture_thought(...)` extracted
- [x] **D7:** Both MCP tools and agent tools refactored to call shared services (thin wrappers only)
- [x] **D8:** Service-level tests added for each extracted service (happy path, review-status, reindex, validation, result shape)
- [x] **D9:** Duplicate tests collapsed — service-level coverage replaces redundant wrapper-level tests

**Rules:**

1. Services own business logic, side effects, reindex queue behavior, and review-status rules.
2. Tool wrappers (both MCP and agent) only validate input format, translate to service call, and serialize output.
3. No new behavior changes — this is a pure extract-and-delegate refactor.

**Acceptance criteria:**

1. All 7 canonical operations implemented once in `monocle/services/`.
2. MCP tools and agent tools are thin wrappers delegating to services.
3. All existing backend tests pass (`uv run python -m pytest monocle/tests/ -x --tb=short -q`).
4. New service-level tests pass.
5. No behavioral regressions detected in E2E tests.

**Test command:** `uv run python -m pytest monocle/tests/ -x --tb=short -q`

---

### M31: MCP Canonicalization

**Goal:** Make the MCP tool layer the authoritative schema definition for Monocle-owned operations.

**Deliverables:**

- [x] **D1:** Each MCP tool maps 1:1 to a shared service function with no inline business logic
- [x] **D2:** MCP tool return contracts documented and frozen (breaking changes require explicit versioned acceptance)
- [x] **D3:** External MCP client backward compatibility verified — existing tool names, input schemas, and output shapes preserved
- [x] **D4:** Contract parity tests added: assert that MCP tool inputs/outputs match the canonical contract table from M29
- [x] **D5:** MCP tool docstrings and OpenAPI descriptions updated to reflect canonical status

**Acceptance criteria:**

1. MCP layer is the authoritative description of Monocle-owned operations.
2. No MCP tool contains business logic beyond input validation and output serialization.
3. Contract parity tests pass.
4. External MCP clients (Claude, Copilot, Cursor) can still use all existing tools without changes.
5. All backend tests pass.

**Test command:** `uv run python -m pytest monocle/tests/ -x --tb=short -q`

---

### M32: Chat Tool Adapter & Orchestration Cleanup

**Status:** COMPLETE (2026-04-09)

**Goal:** Replace agent-tool Monocle business logic with a thin adapter to the canonical service/MCP layer. Verify that chat-only orchestration remains cleanly separated.

**Deliverables:**

- [x] **D1:** Agent tool names in `monocle/agents/tools.py` aligned with MCP canonical names (`fetch_and_summarize_url` → `create_reference_from_url`, `get_person_graph` → `get_graph`)
- [x] **D2:** All Monocle-specific business logic removed from `VaultTools` — each tool delegates to `monocle/services/`; adapter-only responsibilities remain (query resolution, AI merge, wikilink resolution, MemoryIndex fallback, tag normalization)
- [x] **D3:** `fetch_and_summarize_url` resolved per M29-D3 decision — renamed to `create_reference_from_url`, delegates to shared service
- [x] **D4:** Chat-only orchestration verified to remain in `routers/chat.py` (not leaked into canonical tool layer):
  - URL detection and opt-in policy
  - Parallel prefetch batching
  - Context injection into last user message
  - SSE event shaping (`token`, `tool_call`, `tool_error`, `note_created`, `done`)
  - Session and timeout policy
  - Tool-hint policy
- [x] **D5:** Contract parity tests added (6 tests in `TestAdapterMCPOutputParity`): assert agent adapter output keys are superset of MCP output keys, agent tool names match canonical set minus `capture_thought`
- [x] **D6:** 8 obsolete duplicate wrapper tests removed from `TestVaultToolsExecution`; chat integration tests preserved

**Test results:** 881 backend tests, 416 frontend tests passing.

---

### M33: Third-Party MCP Composition

**Goal:** Add explicit support for agent composition across internal Monocle MCP tools, external third-party MCP servers, and lightweight local helpers.

**Deliverables:**

- [ ] **D1:** Agent planner can distinguish Monocle-owned tools from third-party MCP tools
- [ ] **D2:** External MCP server configuration supported (connection config in `config.yaml` or equivalent)
- [ ] **D3:** Agent routing rules documented: use Monocle MCP for Monocle data, external MCP for outside systems, local helper logic only for orchestration or transient transforms
- [ ] **D4:** At least one third-party MCP integration tested end-to-end (e.g., filesystem, web search, or calendar MCP server)
- [ ] **D5:** Documentation updated: how to add a new external MCP server, how tools are composed in a chat session

**Acceptance criteria:**

1. Chat agent can invoke both Monocle-owned and third-party MCP tools in a single session.
2. Monocle-owned tools remain canonical and are not duplicated for third-party composition.
3. Third-party tool failures do not break Monocle-owned tool execution.
4. All backend tests pass.

**Test command:** `uv run python -m pytest monocle/tests/ -x --tb=short -q`

## What Should Remain Non-MCP

Even after the refactor, some logic should stay outside the MCP tool plane:

1. SSE framing and event translation.
2. User-session semantics.
3. URL-pill UI and opt-in behavior.
4. Model/tool-call policy and planner instructions.
5. Response streaming aggregation for telemetry.
6. Chat-specific safety and timeout rules.

These are interaction concerns, not Monocle data operations.

## Key Design Decisions

### 1. Do not make the browser a first-class MCP client

Reason:

1. Browser chat still needs `/api/chat` for streaming UX and orchestration.
2. MCP auth and transport are better kept server-side.
3. Direct browser-to-MCP would complicate security and event shaping without simplifying the backend enough to justify it.

### 2. Avoid HTTP loopback when chat calls Monocle MCP

If chat becomes an internal MCP client, prefer an in-process adapter over calling `http://127.0.0.1:8000/mcp` from the same process.

Reason:

1. Lower latency.
2. Fewer moving parts.
3. No self-auth bootstrapping.
4. Easier tracing and error handling.

### 3. Normalize around MCP names, not chat-specific aliases

Reason:

1. MCP is the desired canonical tool plane.
2. Canonical names reduce planner confusion.
3. External and internal documentation become the same documentation.

## Major Risks

### Risk 1: Breaking existing chat behavior while unifying tools

Mitigation:

1. Keep chat orchestration unchanged during early phases.
2. Refactor business logic first, tool routing second.
3. Preserve current SSE event contracts until the final cleanup phase.

### Risk 2: Tool-schema impedance mismatch between agent framework and MCP

Mitigation:

1. Build explicit schema adapters.
2. Freeze canonical contracts before replacing wrappers.
3. Add contract tests that assert parity of inputs and outputs.

### Risk 3: Over-rotating and turning MCP into a catch-all orchestration layer

Mitigation:

1. Keep MCP focused on Monocle-owned operations.
2. Keep planner/session/UX logic in chat.
3. Keep chat-only prefetch and context injection outside canonical tool handlers.

## Testing Strategy

### Service-level tests

For each extracted shared service:

1. Verify happy path behavior.
2. Verify review-status semantics.
3. Verify reindex semantics.
4. Verify validation and path-boundary behavior.
5. Verify result-shape stability.

### MCP wrapper tests

Keep focused tests for:

1. auth,
2. schema serialization,
3. edge-case input validation,
4. backward compatibility for external clients.

### Chat integration tests

Keep focused tests for:

1. SSE event order,
2. tool_call and note_created events,
3. URL prefetch behavior,
4. context injection,
5. error propagation and timeout handling.

### Contract parity tests

Add tests that assert the internal chat-facing Monocle tool adapter and the MCP tool layer resolve to the same service behavior and result fields.

## Suggested Execution Order

1. **M29** — Document canonical Monocle operations and schemas (no code changes).
2. **M30** — Extract shared service functions; both tool layers become thin wrappers.
3. **M31** — Freeze MCP as the canonical schema layer over shared services.
4. **M32** — Refactor chat tools to delegate; clean up chat-only orchestration boundaries.
5. **M33** — Add third-party MCP composition for external tool servers.

## Definition of Done

This refactor is complete when:

1. Monocle-owned data operations are implemented once, in `monocle/services/` (M30).
2. MCP is the documented canonical tool contract for those operations (M31).
3. Chat still provides the same UX and SSE behavior (M32).
4. External MCP clients retain working access to Monocle data tools (M31).
5. Chat-only orchestration remains outside the canonical Monocle tool plane (M32).
6. Agent-only Monocle tool implementations are either removed or reduced to thin adapters (M32).
7. Third-party MCP tools can be composed alongside Monocle tools in a chat session (M33).

## Bottom-Line Recommendation

Yes: Monocle should move toward a model where the MCP server is the canonical tool plane for Monocle-owned operations, and chat acts as a server-side client of that plane.

No: the browser chat UI should not directly replace `/api/chat` with raw MCP usage.

The right end state is:

1. **MCP for Monocle operations**,
2. **chat for orchestration and streaming UX**,
3. **agent logic for planning and composition**, including third-party MCP usage where appropriate.