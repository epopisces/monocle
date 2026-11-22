import { parse as parseYaml } from "yaml";

export interface ParsedNote {
  frontmatter: Record<string, unknown>;
  /** Set when a frontmatter block exists but is not a valid YAML mapping. */
  frontmatterError: string | null;
  body: string;
}

const FRONTMATTER = /^\uFEFF?---\r?\n([\s\S]*?)\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|$)/;

export function parseNote(content: string): ParsedNote {
  const match = FRONTMATTER.exec(content);
  if (!match) return { frontmatter: {}, frontmatterError: null, body: content.replace(/^\uFEFF/, "") };
  const body = content.slice(match[0].length);
  try {
    const value: unknown = parseYaml(match[1]!);
    if (value === null || value === undefined) return { frontmatter: {}, frontmatterError: null, body };
    if (typeof value !== "object" || Array.isArray(value)) {
      return { frontmatter: {}, frontmatterError: "frontmatter is not a mapping", body };
    }
    return { frontmatter: value as Record<string, unknown>, frontmatterError: null, body };
  } catch (error) {
    return { frontmatter: {}, frontmatterError: (error as Error).message, body };
  }
}

/** Frontmatter `title`, else the first level-1 heading, else the file name without extension. */
export function noteTitle(parsed: ParsedNote, path: string): string {
  const fm = parsed.frontmatter["title"];
  if (typeof fm === "string" && fm.trim()) return fm.trim();
  const heading = /^#[ \t]+(.+?)[ \t#]*$/m.exec(parsed.body);
  if (heading) return heading[1]!.trim();
  const file = path.slice(path.lastIndexOf("/") + 1);
  return file.replace(/\.md$/i, "");
}

export function noteId(parsed: ParsedNote, idField: string): string | null {
  const value = parsed.frontmatter[idField];
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

/** Flattens frontmatter scalar values (recursively) into searchable text. */
export function frontmatterText(frontmatter: Record<string, unknown>): string {
  const out: string[] = [];
  const visit = (value: unknown): void => {
    if (value === null || value === undefined) return;
    if (Array.isArray(value)) value.forEach(visit);
    else if (value instanceof Date) out.push(value.toISOString());
    else if (typeof value === "object") Object.values(value).forEach(visit);
    else out.push(String(value));
  };
  visit(frontmatter);
  return out.join("\n");
}
