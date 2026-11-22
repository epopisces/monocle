import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";

export interface ScannedFile {
  /** Vault-relative path with `/` separators. */
  path: string;
  mtimeMs: number;
  size: number;
}

export interface ScanOptions {
  /** Vault-relative folder prefixes to skip (e.g. `templates`). Dot-folders are always skipped. */
  excludeFolders: readonly string[];
}

function normalizeFolder(folder: string): string {
  return folder.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
}

/** True when a vault-relative path belongs to indexable Markdown content. */
export function isIndexablePath(path: string, options: ScanOptions): boolean {
  const rel = path.replace(/\\/g, "/");
  if (!rel.toLowerCase().endsWith(".md")) return false;
  if (rel.split("/").some((segment) => segment.startsWith("."))) return false;
  return !options.excludeFolders.some((f) => {
    const folder = normalizeFolder(f);
    return folder !== "" && (rel === folder || rel.startsWith(`${folder}/`));
  });
}

export function scanVault(root: string, options: ScanOptions): ScannedFile[] {
  const files: ScannedFile[] = [];
  const walk = (dir: string, rel: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.name.startsWith(".")) continue;
      const childRel = rel ? `${rel}/${entry.name}` : entry.name;
      const abs = join(dir, entry.name);
      if (entry.isDirectory()) walk(abs, childRel);
      else if (entry.isFile() && isIndexablePath(childRel, options)) {
        const stat = statSync(abs);
        files.push({ path: childRel, mtimeMs: stat.mtimeMs, size: stat.size });
      }
    }
  };
  walk(root, "");
  return files.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
}
