import type { EmbeddingProvider } from "@monocle/core";

/** Deterministic bag-of-words embedding: texts sharing words point the same way. */
export function fakeProvider(id = "fake:bow@1"): EmbeddingProvider & { embedded: string[]; fail: boolean } {
  const dims = 64;
  const provider = {
    id,
    locality: "local" as const,
    embedded: [] as string[],
    fail: false,
    async embed(texts: string[]): Promise<number[][]> {
      if (provider.fail) throw new Error("provider offline");
      provider.embedded.push(...texts);
      return texts.map((t) => {
        const v = new Array<number>(dims).fill(0);
        for (const w of t.toLowerCase().match(/[a-z0-9]+/g) ?? []) {
          let h = 0;
          for (const ch of w) h = (h * 31 + ch.charCodeAt(0)) % dims;
          v[h]! += 1;
        }
        return v;
      });
    },
  };
  return provider;
}
