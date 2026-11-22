import type { VectorMatch, VectorRecord, VectorStore } from "./types.js";

function cosineDistance(a: number[], b: number[]): number {
  let dot = 0;
  let na = 0;
  let nb = 0;
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    dot += a[i]! * b[i]!;
    na += a[i]! * a[i]!;
    nb += b[i]! * b[i]!;
  }
  return na === 0 || nb === 0 ? 1 : 1 - dot / Math.sqrt(na * nb);
}

/** Non-persistent vector store for tests and hosts without Chroma. Brute-force cosine search. */
export function createMemoryVectorStore(id = "memory"): VectorStore & { readonly size: number } {
  const records = new Map<string, VectorRecord>();
  return {
    id,
    get size() {
      return records.size;
    },
    async upsert(batch) {
      for (const r of batch) records.set(r.id, structuredClone(r));
    },
    async delete(ids) {
      for (const id of ids) records.delete(id);
    },
    async query(vector, limit): Promise<VectorMatch[]> {
      return [...records.values()]
        .map((r) => ({ id: r.id, distance: cosineDistance(vector, r.vector), text: r.text, metadata: r.metadata }))
        .sort((a, b) => a.distance - b.distance || a.id.localeCompare(b.id))
        .slice(0, limit);
    },
    async reset() {
      records.clear();
    },
  };
}
