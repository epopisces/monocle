import { createHash } from "node:crypto";

/** Bump when chunking output changes; a mismatch forces a semantic rebuild. */
export const CHUNKER_VERSION = 1;

export interface Chunk {
  /**
   * Stable source passage ID: `<vault-relative path>#<12 hex of content hash>`, with `~N` appended for the
   * Nth repeat of identical text in the same note. Unchanged passages keep their ID across edits elsewhere.
   */
  passageId: string;
  path: string;
  /** Position within the note, from 0. */
  ordinal: number;
  /** Heading trail, e.g. `Alpha > Beta`; empty before the first heading. */
  heading: string;
  text: string;
  /** SHA-256 of `text`; the embedding cache key. */
  textHash: string;
}

export interface ChunkOptions {
  /** Soft upper bound on passage length; sections are split on paragraph boundaries. Default 1500. */
  maxChars?: number;
}

const HEADING = /^(#{1,6})[ \t]+(.+?)[ \t#]*$/;
const FENCE = /^[ \t]*(```|~~~)/;

interface Section {
  heading: string;
  text: string;
}

function sections(body: string): Section[] {
  const out: Section[] = [];
  const trail: { level: number; title: string }[] = [];
  let lines: string[] = [];
  let heading = "";
  let fence: string | null = null;
  const flush = (): void => {
    out.push({ heading, text: lines.join("\n") });
    lines = [];
  };
  for (const line of body.split(/\r?\n/)) {
    const f = FENCE.exec(line);
    if (f) fence = fence === null ? f[1]! : fence === f[1] ? null : fence;
    const h = fence === null && !f ? HEADING.exec(line) : null;
    if (h) {
      flush();
      const level = h[1]!.length;
      while (trail.length && trail[trail.length - 1]!.level >= level) trail.pop();
      trail.push({ level, title: h[2]! });
      heading = trail.map((t) => t.title).join(" > ");
    }
    lines.push(line);
  }
  flush();
  return out;
}

function split(text: string, maxChars: number): string[] {
  if (text.length <= maxChars) return [text];
  const out: string[] = [];
  let current = "";
  for (const para of text.split(/\n[ \t]*\n/).map((p) => p.trim()).filter(Boolean)) {
    for (let i = 0; i < para.length; i += maxChars) {
      const piece = para.slice(i, i + maxChars);
      if (current && current.length + 2 + piece.length > maxChars) {
        out.push(current);
        current = "";
      }
      current = current ? `${current}\n\n${piece}` : piece;
    }
  }
  if (current) out.push(current);
  return out;
}

/** Splits a note body (Markdown after frontmatter) into heading-scoped passages for embedding. */
export function chunkNote(path: string, body: string, options: ChunkOptions = {}): Chunk[] {
  const maxChars = options.maxChars ?? 1500;
  const seen = new Map<string, number>();
  const chunks: Chunk[] = [];
  for (const section of sections(body)) {
    const text = section.text.trim();
    // A section holding only its heading line carries nothing to retrieve.
    if (!text || (section.heading && !text.includes("\n"))) continue;
    for (const piece of split(text, maxChars)) {
      const textHash = createHash("sha256").update(piece).digest("hex");
      const base = `${path}#${textHash.slice(0, 12)}`;
      const n = (seen.get(base) ?? 0) + 1;
      seen.set(base, n);
      chunks.push({
        passageId: n === 1 ? base : `${base}~${n}`,
        path,
        ordinal: chunks.length,
        heading: section.heading,
        text: piece,
        textHash,
      });
    }
  }
  return chunks;
}
