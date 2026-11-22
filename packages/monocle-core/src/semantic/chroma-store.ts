import { postJson, type FetchLike } from "./http.js";
import type { PassageMetadata, VectorMatch, VectorStore } from "./types.js";

export interface ChromaStoreOptions {
  /** Chroma server root. Default `http://127.0.0.1:8000`. */
  url?: string;
  tenant?: string;
  database?: string;
  /** Default `monocle`. */
  collection?: string;
  /** Sent as `x-chroma-token` when the server requires auth. */
  token?: string;
  fetch?: FetchLike;
}

type ChromaMetadata = Record<string, string | number | boolean>;

function toChroma(m: PassageMetadata): ChromaMetadata {
  const { noteId, ...rest } = m;
  return noteId === null ? rest : { ...rest, noteId };
}

function fromChroma(m: ChromaMetadata | null | undefined): PassageMetadata {
  const v = m ?? {};
  return {
    path: String(v["path"] ?? ""),
    noteId: v["noteId"] === undefined ? null : String(v["noteId"]),
    noteHash: String(v["noteHash"] ?? ""),
    heading: String(v["heading"] ?? ""),
    ordinal: Number(v["ordinal"] ?? 0),
    textHash: String(v["textHash"] ?? ""),
  };
}

/** ChromaDB over its v2 REST API (Chroma ≥ 1.0 server). Derived storage only; Markdown stays authoritative. */
export function createChromaVectorStore(options: ChromaStoreOptions = {}): VectorStore {
  const url = (options.url ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
  const tenant = options.tenant ?? "default_tenant";
  const database = options.database ?? "default_database";
  const name = options.collection ?? "monocle";
  const fetch = options.fetch ?? globalThis.fetch;
  const headers: Record<string, string> = options.token ? { "x-chroma-token": options.token } : {};
  const collections = `${url}/api/v2/tenants/${encodeURIComponent(tenant)}/databases/${encodeURIComponent(database)}/collections`;
  let collectionId: string | null = null;

  const collection = async (): Promise<string> => {
    if (!collectionId) {
      const out = (await postJson(
        fetch,
        collections,
        { name, get_or_create: true, configuration: { hnsw: { space: "cosine" } } },
        headers,
      )) as { id: string };
      collectionId = out.id;
    }
    return `${collections}/${collectionId}`;
  };

  return {
    id: `chroma:${url}/${tenant}/${database}/${name}`,
    async upsert(records) {
      const at = await collection();
      if (!records.length) return;
      await postJson(
        fetch,
        `${at}/upsert`,
        {
          ids: records.map((r) => r.id),
          embeddings: records.map((r) => r.vector),
          documents: records.map((r) => r.text),
          metadatas: records.map((r) => toChroma(r.metadata)),
        },
        headers,
      );
    },
    async delete(ids) {
      if (!ids.length) return;
      await postJson(fetch, `${await collection()}/delete`, { ids }, headers);
    },
    async query(vector, limit): Promise<VectorMatch[]> {
      const out = (await postJson(
        fetch,
        `${await collection()}/query`,
        { query_embeddings: [vector], n_results: limit, include: ["documents", "metadatas", "distances"] },
        headers,
      )) as {
        ids: string[][];
        distances?: (number | null)[][] | null;
        documents?: (string | null)[][] | null;
        metadatas?: (ChromaMetadata | null)[][] | null;
      };
      return (out.ids[0] ?? []).map((id, i) => ({
        id,
        distance: out.distances?.[0]?.[i] ?? 1,
        text: out.documents?.[0]?.[i] ?? "",
        metadata: fromChroma(out.metadatas?.[0]?.[i]),
      }));
    },
    async reset() {
      collectionId = null;
      try {
        await postJson(fetch, `${collections}/${encodeURIComponent(name)}`, undefined, headers, "DELETE");
      } catch (error) {
        if (!/\b404\b/.test((error as Error).message)) throw error;
      }
    },
  };
}
