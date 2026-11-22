import { describe, expect, it } from "vitest";
import {
  RemoteEmbeddingNotPermittedError,
  createChromaVectorStore,
  createOllamaEmbeddingProvider,
  createOpenAICompatibleEmbeddingProvider,
  createSemanticIndexFromConfig,
  openNoteIndex,
} from "@monocle/core";

interface Call {
  method: string;
  url: string;
  body: unknown;
  headers: Record<string, string>;
}

/** Fake HTTP server: routes `METHOD path-suffix` to a JSON response and records every request. */
function fakeFetch(routes: Record<string, unknown | ((body: any) => unknown)>) {
  const calls: Call[] = [];
  const fetch = async (input: string | URL | Request, init?: RequestInit): Promise<Response> => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, url, body, headers: Object.fromEntries(new Headers(init?.headers).entries()) });
    const key = Object.keys(routes).find((k) => {
      const [m, suffix] = k.split(" ");
      return m === method && url.endsWith(suffix!);
    });
    if (!key) return new Response("not found", { status: 404 });
    const route = routes[key];
    const value = typeof route === "function" ? (route as (b: unknown) => unknown)(body) : route;
    return new Response(JSON.stringify(value), { status: 200, headers: { "content-type": "application/json" } });
  };
  return { fetch: fetch as typeof globalThis.fetch, calls };
}

describe("embedding providers", () => {
  it("defaults to a local Ollama model", async () => {
    const http = fakeFetch({ "POST /api/embed": { embeddings: [[1, 0], [0, 1]] } });
    const provider = createOllamaEmbeddingProvider({ fetch: http.fetch });
    expect(provider).toMatchObject({ id: "ollama:nomic-embed-text", locality: "local" });
    expect(await provider.embed(["a", "b"])).toEqual([[1, 0], [0, 1]]);
    expect(http.calls[0]).toMatchObject({
      url: "http://127.0.0.1:11434/api/embed",
      body: { model: "nomic-embed-text", input: ["a", "b"] },
    });
  });

  it("calls an OpenAI-compatible endpoint, ordering vectors by index, and classifies its locality", async () => {
    const http = fakeFetch({
      "POST /v1/embeddings": { data: [{ index: 1, embedding: [2] }, { index: 0, embedding: [1] }] },
    });
    const remote = createOpenAICompatibleEmbeddingProvider({
      baseUrl: "https://api.example.com/v1",
      model: "text-embedding-3-small",
      apiKey: "sk-test",
      fetch: http.fetch,
    });
    expect(remote).toMatchObject({ locality: "remote", id: "openai-compatible:api.example.com/text-embedding-3-small" });
    expect(await remote.embed(["x", "y"])).toEqual([[1], [2]]);
    expect(http.calls[0]!.headers["authorization"]).toBe("Bearer sk-test");

    const lmStudio = createOpenAICompatibleEmbeddingProvider({ baseUrl: "http://localhost:1234/v1", model: "m" });
    expect(lmStudio.locality).toBe("local");
  });

  it("surfaces HTTP failures as errors", async () => {
    const http = fakeFetch({});
    await expect(createOllamaEmbeddingProvider({ fetch: http.fetch }).embed(["a"])).rejects.toThrow(/404/);
  });
});

describe("Chroma vector store", () => {
  const base = "http://127.0.0.1:8000/api/v2/tenants/default_tenant/databases/default_database/collections";

  it("creates a cosine collection lazily and maps upsert/query/delete to the v2 REST API", async () => {
    const http = fakeFetch({
      "POST /collections": { id: "c-1", name: "monocle" },
      "POST /c-1/upsert": {},
      "POST /c-1/delete": {},
      "POST /c-1/query": {
        ids: [["p.md#aaa"]],
        distances: [[0.25]],
        documents: [["text"]],
        metadatas: [[{ path: "p.md", noteHash: "h", heading: "H", ordinal: 0, textHash: "t" }]],
      },
    });
    const store = createChromaVectorStore({ fetch: http.fetch, token: "tok" });
    expect(store.id).toBe("chroma:http://127.0.0.1:8000/default_tenant/default_database/monocle");

    await store.upsert([
      {
        id: "p.md#aaa",
        vector: [1, 2],
        text: "text",
        metadata: { path: "p.md", noteId: null, noteHash: "h", heading: "H", ordinal: 0, textHash: "t" },
      },
    ]);
    const matches = await store.query([1, 2], 3);
    await store.delete(["p.md#aaa"]);

    expect(http.calls.map((c) => `${c.method} ${c.url}`)).toEqual([
      `POST ${base}`,
      `POST ${base}/c-1/upsert`,
      `POST ${base}/c-1/query`,
      `POST ${base}/c-1/delete`,
    ]);
    expect(http.calls[0]!.body).toMatchObject({ name: "monocle", get_or_create: true, configuration: { hnsw: { space: "cosine" } } });
    expect(http.calls[0]!.headers["x-chroma-token"]).toBe("tok");
    // Chroma metadata cannot hold null, so a missing note ID is omitted and restored as null.
    expect(http.calls[1]!.body).toEqual({
      ids: ["p.md#aaa"],
      embeddings: [[1, 2]],
      documents: ["text"],
      metadatas: [{ path: "p.md", noteHash: "h", heading: "H", ordinal: 0, textHash: "t" }],
    });
    expect(http.calls[2]!.body).toMatchObject({ query_embeddings: [[1, 2]], n_results: 3 });
    expect(matches).toEqual([
      {
        id: "p.md#aaa",
        distance: 0.25,
        text: "text",
        metadata: { path: "p.md", noteId: null, noteHash: "h", heading: "H", ordinal: 0, textHash: "t" },
      },
    ]);
  });

  it("reset deletes the collection and recreates it on next use", async () => {
    const http = fakeFetch({ "POST /collections": { id: "c-2" }, "DELETE /collections/monocle": {}, "POST /c-2/upsert": {} });
    const store = createChromaVectorStore({ fetch: http.fetch });
    await store.reset();
    await store.upsert([]);
    expect(http.calls.map((c) => c.method)).toEqual(["DELETE", "POST"]);
  });
});

describe("semantic configuration", () => {
  const noteIndex = () => openNoteIndex({ vaultRoot: ".", dbPath: ":memory:" });

  it("is off unless enabled, so lexical search needs no semantic dependencies", () => {
    const index = noteIndex();
    expect(createSemanticIndexFromConfig(undefined, { noteIndex: index, statePath: ":memory:" })).toBeUndefined();
    expect(createSemanticIndexFromConfig({ enabled: false }, { noteIndex: index, statePath: ":memory:" })).toBeUndefined();
    index.close();
  });

  it("defaults to local Ollama + Chroma and refuses remote providers unless policy permits them", () => {
    const index = noteIndex();
    const local = createSemanticIndexFromConfig({ enabled: true }, { noteIndex: index, statePath: ":memory:" })!;
    expect(local.status()).toMatchObject({
      providerId: "ollama:nomic-embed-text",
      storeId: "chroma:http://127.0.0.1:8000/default_tenant/default_database/monocle",
    });
    local.close();

    const remote = {
      enabled: true,
      provider: { kind: "openai-compatible", baseUrl: "https://api.example.com/v1", model: "m" },
    } as const;
    expect(() => createSemanticIndexFromConfig(remote, { noteIndex: index, statePath: ":memory:" })).toThrow(
      RemoteEmbeddingNotPermittedError,
    );
    const allowed = createSemanticIndexFromConfig(
      { ...remote, allowRemoteProviders: true },
      { noteIndex: index, statePath: ":memory:" },
    )!;
    expect(allowed.providerId).toBe("openai-compatible:api.example.com/m");
    allowed.close();
    index.close();
  });
});
