import type { NoteIndex } from "../note-index/note-index.js";
import type { SemanticIndex } from "./semantic-index.js";

export type RetrievalMode = "hybrid" | "lexical" | "semantic";
export type RetrievalSource = "lexical" | "semantic";

export interface SourcePassage {
  passageId: string;
  heading: string;
  text: string;
  /** Cosine distance; lower is closer. */
  distance: number;
  /** The note changed after this passage was embedded. */
  stale: boolean;
}

export interface RetrievalHit {
  path: string;
  id: string | null;
  title: string;
  /** Lexical excerpt with matches in `[` `]`; null when only semantic retrieval matched. */
  snippet: string | null;
  /** Semantic source passages for this note, closest first; empty for lexical-only hits. */
  passages: SourcePassage[];
  sources: RetrievalSource[];
  /** Reciprocal-rank-fusion score; higher is more relevant. */
  score: number;
}

export interface RetrievalResult {
  hits: RetrievalHit[];
  /**
   * `disabled`: no semantic index configured; `skipped`: lexical mode; `unavailable`: provider/store failed,
   * so results are lexical only.
   */
  semantic: { status: "ok" | "disabled" | "skipped" | "unavailable"; error: string | null };
}

export interface RetrievalOptions {
  limit?: number;
  /**
   * `hybrid` (default) fuses lexical and semantic ranks. `semantic` ranks by passages only, but still answers
   * lexically when semantic retrieval is disabled or unavailable.
   */
  mode?: RetrievalMode;
}

export interface Retriever {
  search(query: string, options?: RetrievalOptions): Promise<RetrievalResult>;
}

export interface RetrieverOptions {
  noteIndex: NoteIndex;
  semantic?: SemanticIndex | undefined;
  /** Reciprocal-rank-fusion constant. Default 60. */
  rrfK?: number;
}

/** One query/result interface over SQLite FTS5 and optional semantic passages. Lexical never depends on semantic. */
export function createRetriever(options: RetrieverOptions): Retriever {
  const k = options.rrfK ?? 60;
  return {
    async search(query, { limit = 20, mode = "hybrid" } = {}) {
      let semantic: RetrievalResult["semantic"] = { status: "disabled", error: null };
      let passages: Awaited<ReturnType<SemanticIndex["search"]>> = [];
      if (mode === "lexical") semantic = { status: "skipped", error: null };
      else if (options.semantic) {
        try {
          passages = await options.semantic.search(query, { limit: limit * 3 });
          semantic = { status: "ok", error: null };
        } catch (error) {
          semantic = { status: "unavailable", error: (error as Error).message };
        }
      }
      const useLexical = mode !== "semantic" || semantic.status !== "ok";
      const lexical = useLexical ? options.noteIndex.search(query, { limit: limit * 3 }) : [];

      const hits = new Map<string, RetrievalHit>();
      lexical.forEach((h, rank) => {
        hits.set(h.path, {
          path: h.path,
          id: h.id,
          title: h.title,
          snippet: h.snippet,
          passages: [],
          sources: ["lexical"],
          score: 1 / (k + rank + 1),
        });
      });
      let noteRank = 0;
      for (const p of passages) {
        let hit = hits.get(p.path);
        const passage = { passageId: p.passageId, heading: p.heading, text: p.text, distance: p.distance, stale: p.stale };
        if (hit?.sources.includes("semantic")) {
          hit.passages.push(passage);
          continue;
        }
        const score = 1 / (k + ++noteRank);
        if (hit) {
          hit.sources.push("semantic");
          hit.score += score;
        } else {
          hit = { path: p.path, id: p.noteId, title: p.title, snippet: null, passages: [], sources: ["semantic"], score };
          hits.set(p.path, hit);
        }
        hit.passages.push(passage);
      }
      return {
        hits: [...hits.values()].sort((a, b) => b.score - a.score || a.path.localeCompare(b.path)).slice(0, limit),
        semantic,
      };
    },
  };
}
