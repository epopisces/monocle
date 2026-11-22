import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { CONTRACT_VERSION, isContractCompatible, type PackageDescriptor } from "@monocle/contracts";

const packagesDir = fileURLToPath(new URL("../packages/", import.meta.url));

/**
 * Allowed workspace dependencies, from the MVP spec: Cravat is independent of Monocle knowledge
 * services; the companion hosts both; the Obsidian plugin is a thin client that only shares
 * contracts with the companion.
 */
const ALLOWED: Record<string, string[]> = {
  "@monocle/contracts": [],
  "@monocle/core": ["@monocle/contracts"],
  "@monocle/cravat": ["@monocle/contracts"],
  "@monocle/companion": ["@monocle/contracts", "@monocle/core", "@monocle/cravat"],
  "@monocle/obsidian-plugin": ["@monocle/contracts"],
};

const workspaces = readdirSync(packagesDir, { withFileTypes: true })
  .filter((d) => d.isDirectory())
  .map((d) => {
    const dir = join(packagesDir, d.name);
    const manifest = JSON.parse(readFileSync(join(dir, "package.json"), "utf8")) as {
      name: string;
      dependencies?: Record<string, string>;
      devDependencies?: Record<string, string>;
    };
    return { dir, manifest };
  });

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true, recursive: true })
    .filter((e) => e.isFile() && e.name.endsWith(".ts"))
    .map((e) => join(e.parentPath, e.name));
}

describe("workspace package contract", () => {
  it("contains exactly the planned package boundaries", () => {
    expect(workspaces.map((w) => w.manifest.name).sort()).toEqual(Object.keys(ALLOWED).sort());
  });

  describe.each(workspaces.map((w) => [w.manifest.name, w] as const))("%s", (name, ws) => {
    it("exports a descriptor matching its manifest and a compatible contract version", async () => {
      const mod = (await import(name)) as { packageDescriptor?: PackageDescriptor };
      expect(mod.packageDescriptor?.name).toBe(name);
      expect(
        isContractCompatible({ local: CONTRACT_VERSION, remote: mod.packageDescriptor?.contractVersion ?? "" }),
      ).toBe(true);
    });

    it("declares only allowed workspace dependencies", () => {
      const declared = Object.keys({ ...ws.manifest.dependencies, ...ws.manifest.devDependencies }).filter((d) =>
        d.startsWith("@monocle/"),
      );
      expect(declared.filter((d) => !ALLOWED[name]!.includes(d))).toEqual([]);
    });

    it("imports only workspace packages it declares", () => {
      const declared = new Set(Object.keys(ws.manifest.dependencies ?? {}));
      const imported = new Set<string>();
      for (const file of sourceFiles(join(ws.dir, "src"))) {
        for (const m of readFileSync(file, "utf8").matchAll(/from\s+["'](@monocle\/[^"'/]+)/g)) imported.add(m[1]!);
      }
      imported.delete(name);
      expect([...imported].filter((i) => !declared.has(i))).toEqual([]);
    });
  });
});
