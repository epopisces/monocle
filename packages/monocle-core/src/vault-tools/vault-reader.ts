import { readFileSync, realpathSync, statSync } from "node:fs";
import { isAbsolute, join, relative, sep } from "node:path";
import { scanVault } from "../note-index/scan.js";

/** Largest note body returned by one read; longer notes are cut and flagged. */
export const MAX_NOTE_READ_LENGTH = 100_000;

export interface VaultReaderOptions {
  readonly vaultRoot: string;
  /** Vault-relative notes or folders that must never be read, listed or searched. */
  readonly exclude?: readonly string[];
}

export interface NoteContent {
  readonly path: string;
  readonly content: string;
  readonly truncated: boolean;
}

export interface NoteSearchHit {
  readonly path: string;
  readonly snippet: string;
}

/** Raised for any path a vault reader refuses; the message is safe to show to the model. */
export class VaultAccessError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "VaultAccessError";
  }
}

const normalize = (p: string) => p.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");

/**
 * Validates a client- or model-supplied vault-relative path syntactically, without touching the filesystem.
 * Rejects absolute paths, `..`/`.` segments, hidden (dot) segments such as `.obsidian`, and NUL bytes.
 */
export function checkVaultRelativePath(path: string): string {
  if (typeof path !== "string" || path.trim() === "") throw new VaultAccessError("path must be a non-empty string");
  if (path.includes("\0")) throw new VaultAccessError("path contains a NUL byte");
  const slashed = path.replace(/\\/g, "/");
  if (slashed.startsWith("/") || /^[a-zA-Z]:/.test(slashed) || isAbsolute(path)) {
    throw new VaultAccessError(`path must be vault-relative: ${path}`);
  }
  const segments = slashed.split("/");
  if (segments.some((s) => s === "" || s === "." || s === "..")) {
    throw new VaultAccessError(`path may not contain empty, "." or ".." segments: ${path}`);
  }
  if (segments.some((s) => s.startsWith("."))) throw new VaultAccessError(`hidden files and folders are not accessible: ${path}`);
  return segments.join("/");
}

/** Compiled exclusion list. Matching is case-insensitive because vault file systems often are. */
export class VaultExclusions {
  private readonly entries: string[];

  constructor(exclude: readonly string[] = []) {
    this.entries = exclude.map((e) => normalize(e).toLowerCase()).filter((e) => e !== "");
  }

  has(path: string): boolean {
    const p = normalize(path).toLowerCase();
    return this.entries.some((e) => p === e || p.startsWith(`${e}/`));
  }
}

/**
 * Read-only access to Markdown notes inside one vault. Every path is confined to the vault (including after
 * resolving symlinks/junctions), hidden folders and non-Markdown files are refused, and exclusions apply to
 * every operation. Only filesystem read APIs are used.
 */
export class VaultReader {
  readonly exclusions: VaultExclusions;
  private readonly realRoot: string;

  constructor(options: VaultReaderOptions) {
    this.realRoot = realpathSync.native(options.vaultRoot);
    this.exclusions = new VaultExclusions(options.exclude);
  }

  isExcluded(path: string): boolean {
    return this.exclusions.has(path);
  }

  readNote(path: string): NoteContent {
    const rel = this.resolveNote(path);
    const raw = readFileSync(join(this.realRoot, rel), "utf8");
    const truncated = raw.length > MAX_NOTE_READ_LENGTH;
    return { path: rel, content: truncated ? raw.slice(0, MAX_NOTE_READ_LENGTH) : raw, truncated };
  }

  /** Vault-relative paths of readable notes, optionally under `folder`. */
  listNotes(folder?: string): string[] {
    const prefix = folder === undefined || normalize(folder) === "" ? "" : `${checkVaultRelativePath(normalize(folder))}/`.toLowerCase();
    return scanVault(this.realRoot, { excludeFolders: [] })
      .map((f) => f.path)
      .filter((p) => p.toLowerCase().startsWith(prefix) && !this.isExcluded(p));
  }

  /** Case-insensitive search for notes whose path or text contains every whitespace-separated term. */
  searchNotes(query: string, limit = 20): NoteSearchHit[] {
    const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
    if (terms.length === 0) throw new VaultAccessError("query must contain at least one term");
    const hits: NoteSearchHit[] = [];
    for (const path of this.listNotes()) {
      let content: string;
      try {
        content = this.readNote(path).content;
      } catch {
        continue;
      }
      const haystack = `${path}\n${content}`.toLowerCase();
      if (!terms.every((t) => haystack.includes(t))) continue;
      const at = Math.max(0, content.toLowerCase().indexOf(terms[0]!));
      const snippet = content.slice(Math.max(0, at - 60), at + 100).replace(/\s+/g, " ").trim();
      hits.push({ path, snippet });
      if (hits.length >= limit) break;
    }
    return hits;
  }

  /** Returns the canonical vault-relative path of a readable note, or throws {@link VaultAccessError}. */
  resolveNote(path: string): string {
    const rel = checkVaultRelativePath(path);
    if (!rel.toLowerCase().endsWith(".md")) throw new VaultAccessError(`only Markdown notes (.md) can be read: ${path}`);
    if (this.isExcluded(rel)) throw new VaultAccessError(`note is excluded from this request: ${path}`);
    let real: string;
    try {
      real = realpathSync.native(join(this.realRoot, rel));
    } catch {
      throw new VaultAccessError(`note not found: ${path}`);
    }
    const inside = relative(this.realRoot, real);
    if (inside === "" || inside.startsWith("..") || isAbsolute(inside)) throw new VaultAccessError(`path resolves outside the vault: ${path}`);
    const canonical = checkVaultRelativePath(inside.split(sep).join("/"));
    if (this.isExcluded(canonical)) throw new VaultAccessError(`note is excluded from this request: ${path}`);
    if (!statSync(real).isFile()) throw new VaultAccessError(`not a note file: ${path}`);
    return canonical;
  }
}
