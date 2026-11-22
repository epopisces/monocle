import type { NoteIndex } from "../note-index/note-index.js";
import { createChromaVectorStore, type ChromaStoreOptions } from "./chroma-store.js";
import {
  assertEmbeddingPolicy,
  createOllamaEmbeddingProvider,
  createOpenAICompatibleEmbeddingProvider,
  type FetchLike,
} from "./embedding-providers.js";
import { createMemoryVectorStore } from "./memory-store.js";
import { openSemanticIndex, type SemanticIndex } from "./semantic-index.js";
import type { EmbeddingProvider, VectorStore } from "./types.js";

/** Host-local semantic retrieval settings. Absent or `enabled: false` means lexical-only. */
export interface SemanticConfig {
  enabled: boolean;
  /** Default: local Ollama `nomic-embed-text`. */
  provider?:
    | { kind: "ollama"; baseUrl?: string; model?: string }
    | { kind: "openai-compatible"; baseUrl: string; model: string; apiKey?: string };
  /** Policy gate for providers that send note text off this host. Default false. */
  allowRemoteProviders?: boolean;
  /** Default: Chroma at `http://127.0.0.1:8000`. `memory` is non-persistent (tests/diagnostics). */
  store?: ({ kind: "chroma" } & Omit<ChromaStoreOptions, "fetch">) | { kind: "memory" };
  queue?: { delayMs?: number; batchSize?: number; maxPending?: number; retryMs?: number };
  chunk?: { maxChars?: number };
}

export interface SemanticDeps {
  noteIndex: NoteIndex;
  /** Host-local SQLite file for semantic bookkeeping. */
  statePath: string;
  fetch?: FetchLike;
  onError?: (error: Error) => void;
}

function createProvider(config: SemanticConfig, fetch: FetchLike | undefined): EmbeddingProvider {
  const p = config.provider ?? { kind: "ollama" };
  const f = fetch ? { fetch } : {};
  return p.kind === "ollama"
    ? createOllamaEmbeddingProvider({
        ...(p.baseUrl ? { baseUrl: p.baseUrl } : {}),
        ...(p.model ? { model: p.model } : {}),
        ...f,
      })
    : createOpenAICompatibleEmbeddingProvider({
        baseUrl: p.baseUrl,
        model: p.model,
        ...(p.apiKey ? { apiKey: p.apiKey } : {}),
        ...f,
      });
}

function createStore(config: SemanticConfig, fetch: FetchLike | undefined): VectorStore {
  const s = config.store ?? { kind: "chroma" };
  if (s.kind === "memory") return createMemoryVectorStore();
  const { kind: _kind, ...chroma } = s;
  return createChromaVectorStore({ ...chroma, ...(fetch ? { fetch } : {}) });
}

/**
 * Builds the optional semantic index, or returns undefined when disabled. Throws
 * `RemoteEmbeddingNotPermittedError` for a remote provider without `allowRemoteProviders`.
 * Nothing contacts the provider or store until the first background run or search.
 */
export function createSemanticIndexFromConfig(
  config: SemanticConfig | undefined,
  deps: SemanticDeps,
): SemanticIndex | undefined {
  if (!config?.enabled) return undefined;
  const provider = createProvider(config, deps.fetch);
  assertEmbeddingPolicy(provider, config);
  const q = config.queue ?? {};
  return openSemanticIndex({
    noteIndex: deps.noteIndex,
    provider,
    store: createStore(config, deps.fetch),
    statePath: deps.statePath,
    ...(q.delayMs !== undefined ? { delayMs: q.delayMs } : {}),
    ...(q.batchSize !== undefined ? { batchSize: q.batchSize } : {}),
    ...(q.maxPending !== undefined ? { maxPending: q.maxPending } : {}),
    ...(q.retryMs !== undefined ? { retryMs: q.retryMs } : {}),
    ...(config.chunk ? { chunk: config.chunk } : {}),
    ...(deps.onError ? { onError: deps.onError } : {}),
  });
}
