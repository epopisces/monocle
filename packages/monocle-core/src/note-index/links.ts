import type { ParsedNote } from "./markdown.js";

export type LinkKind = "wikilink" | "embed" | "frontmatter";

/** 1-based position of a link's opening brackets in the note file. */
export interface SourceLocation {
  line: number;
  column: number;
}

/** An explicit link exactly as written in one note; resolution happens against the whole vault later. */
export interface ExtractedLink {
  kind: LinkKind;
  /** `links_to` / `embeds` for body links; for frontmatter, a sibling `relation` value or the top-level key. */
  relation: string;
  /** Frontmatter key path (e.g. `links[0].target`), or null for body links. */
  field: string | null;
  raw: string;
  /** Link target without subpath or display text (e.g. `Project Lantern`). Empty for same-note links. */
  target: string;
  /** Heading or block reference after `#`, without the `#`. */
  subpath: string | null;
  /** Display text after `|`. */
  display: string | null;
  location: SourceLocation | null;
}

const WIKILINK = /(!?)\[\[([^[\]\n]+?)\]\]/g;

function parseInner(inner: string): Pick<ExtractedLink, "target" | "subpath" | "display"> {
  const bar = inner.indexOf("|");
  // Inside Markdown tables Obsidian links escape the pipe as `\|`.
  const targetPart = (bar < 0 ? inner : inner.slice(0, bar)).replace(/\\$/, "");
  const display = bar < 0 ? null : inner.slice(bar + 1).trim() || null;
  const hash = targetPart.indexOf("#");
  const target = (hash < 0 ? targetPart : targetPart.slice(0, hash)).trim();
  const subpath = hash < 0 ? null : targetPart.slice(hash + 1).trim() || null;
  return { target, subpath, display };
}

/** Replaces fenced code blocks and inline code with spaces so offsets are preserved but links inside are ignored. */
function maskCode(text: string): string {
  const lines = text.split("\n");
  let fence: string | null = null;
  const masked = lines.map((line) => {
    const opener = /^\s{0,3}(`{3,}|~{3,})/.exec(line);
    if (fence) {
      if (opener && opener[1]!.startsWith(fence)) fence = null;
      return " ".repeat(line.length);
    }
    if (opener) {
      fence = opener[1]!;
      return " ".repeat(line.length);
    }
    return line.replace(/(`+)[^`]*?\1/g, (m) => " ".repeat(m.length));
  });
  return masked.join("\n");
}

function locator(text: string): (offset: number) => SourceLocation {
  const starts = [0];
  for (let i = 0; i < text.length; i++) if (text[i] === "\n") starts.push(i + 1);
  return (offset) => {
    let lo = 0;
    let hi = starts.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (starts[mid]! <= offset) lo = mid;
      else hi = mid - 1;
    }
    return { line: lo + 1, column: offset - starts[lo]! + 1 };
  };
}

/** Extracts explicit wikilinks from the body and wikilink-valued frontmatter properties. Nothing is inferred. */
export function extractLinks(content: string, parsed: ParsedNote): ExtractedLink[] {
  const text = content.replace(/^\uFEFF/, "");
  const bodyStart = text.length - parsed.body.length;
  const locate = locator(text);
  const links: ExtractedLink[] = [];

  let cursor = 0;
  const visit = (value: unknown, field: string, relation: string): void => {
    if (typeof value === "string") {
      for (const m of value.matchAll(WIKILINK)) {
        const found = text.indexOf(m[0], cursor);
        const located = found >= 0 && found < bodyStart;
        if (located) cursor = found + m[0].length;
        links.push({
          kind: "frontmatter",
          relation,
          field,
          raw: m[0],
          ...parseInner(m[2]!),
          location: located ? locate(found) : null,
        });
      }
    } else if (Array.isArray(value)) {
      value.forEach((item, i) => visit(item, `${field}[${i}]`, relation));
    } else if (value !== null && typeof value === "object" && !(value instanceof Date)) {
      const record = value as Record<string, unknown>;
      const own = typeof record["relation"] === "string" && record["relation"].trim() ? record["relation"].trim() : null;
      for (const [key, child] of Object.entries(record)) visit(child, `${field}.${key}`, own ?? relation);
    }
  };
  for (const [key, value] of Object.entries(parsed.frontmatter)) visit(value, key, key);

  const body = maskCode(parsed.body);
  for (const m of body.matchAll(WIKILINK)) {
    const embed = m[1] === "!";
    links.push({
      kind: embed ? "embed" : "wikilink",
      relation: embed ? "embeds" : "links_to",
      field: null,
      raw: m[0],
      ...parseInner(m[2]!),
      location: locate(bodyStart + m.index!),
    });
  }
  return links;
}
