import { postJson, type FetchLike } from "./http.js";
import type { EmbeddingProvider } from "./types.js";

export type { FetchLike } from "./http.js";

export class RemoteEmbeddingNotPermittedError extends Error {
  constructor(readonly providerId: string) {
    super(`Embedding provider ${providerId} sends note text off this host; enable allowRemoteProviders to permit it`);
    this.name = "RemoteEmbeddingNotPermittedError";
  }
}

const LOOPBACK = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);

/** Loopback endpoints (Ollama, LM Studio, a local proxy) are local; anything else is remote. */
export function endpointLocality(baseUrl: string): "local" | "remote" {
  return LOOPBACK.has(new URL(baseUrl).hostname) ? "local" : "remote";
}

export function assertEmbeddingPolicy(provider: EmbeddingProvider, policy: { allowRemoteProviders?: boolean }): void {
  if (provider.locality === "remote" && !policy.allowRemoteProviders) {
    throw new RemoteEmbeddingNotPermittedError(provider.id);
  }
}

const trimSlash = (url: string): string => url.replace(/\/+$/, "");

export interface OllamaEmbeddingOptions {
  /** Default `http://127.0.0.1:11434`. */
  baseUrl?: string;
  /** Default `nomic-embed-text` (provisional; choose per host). */
  model?: string;
  fetch?: FetchLike;
}

/** Local default: Ollama's `/api/embed`. */
export function createOllamaEmbeddingProvider(options: OllamaEmbeddingOptions = {}): EmbeddingProvider {
  const baseUrl = trimSlash(options.baseUrl ?? "http://127.0.0.1:11434");
  const model = options.model ?? "nomic-embed-text";
  const fetch = options.fetch ?? globalThis.fetch;
  return {
    id: `ollama:${model}`,
    locality: endpointLocality(baseUrl),
    async embed(texts) {
      if (!texts.length) return [];
      const out = (await postJson(fetch, `${baseUrl}/api/embed`, { model, input: texts })) as { embeddings: number[][] };
      return out.embeddings;
    },
  };
}

export interface OpenAICompatibleEmbeddingOptions {
  /** API root including version, e.g. `https://api.openai.com/v1` or `http://localhost:1234/v1`. */
  baseUrl: string;
  model: string;
  apiKey?: string;
  fetch?: FetchLike;
}

/** Any `/embeddings` endpoint in the OpenAI shape. Remote unless the host is loopback. */
export function createOpenAICompatibleEmbeddingProvider(options: OpenAICompatibleEmbeddingOptions): EmbeddingProvider {
  const baseUrl = trimSlash(options.baseUrl);
  const fetch = options.fetch ?? globalThis.fetch;
  const headers: Record<string, string> = options.apiKey ? { authorization: `Bearer ${options.apiKey}` } : {};
  return {
    id: `openai-compatible:${new URL(baseUrl).host}/${options.model}`,
    locality: endpointLocality(baseUrl),
    async embed(texts) {
      if (!texts.length) return [];
      const out = (await postJson(fetch, `${baseUrl}/embeddings`, { model: options.model, input: texts }, headers)) as {
        data: { index: number; embedding: number[] }[];
      };
      return [...out.data].sort((a, b) => a.index - b.index).map((d) => d.embedding);
    },
  };
}
