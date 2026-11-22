// Bundles the plugin into an installable Obsidian plugin folder (main.js, manifest.json, styles.css).
// Usage: node scripts/bundle.mjs [--out <dir>] [--vault <vault path>]
//   --vault installs into <vault>/.obsidian/plugins/<manifest id>/ (use the fixture vault, not a production vault).
import { copyFileSync, mkdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { build } from "esbuild";

const pkgDir = fileURLToPath(new URL("..", import.meta.url));

export async function bundle({ outDir }) {
  mkdirSync(outDir, { recursive: true });
  await build({
    entryPoints: [join(pkgDir, "src", "main.ts")],
    outfile: join(outDir, "main.js"),
    bundle: true,
    format: "cjs",
    platform: "browser",
    target: "es2022",
    external: ["obsidian", "electron", "@codemirror/*", "@lezer/*"],
    // Bundle workspace contracts from source so the bundle does not depend on a prior tsc build.
    alias: { "@monocle/contracts": join(pkgDir, "..", "contracts", "src", "index.ts") },
    logLevel: "warning",
    sourcemap: "inline",
  });
  for (const file of ["manifest.json", "styles.css"]) copyFileSync(join(pkgDir, file), join(outDir, file));
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const { values } = parseArgs({ options: { out: { type: "string" }, vault: { type: "string" } } });
  const { id } = JSON.parse(readFileSync(join(pkgDir, "manifest.json"), "utf8"));
  const outDir = values.vault
    ? join(resolve(values.vault), ".obsidian", "plugins", id)
    : resolve(values.out ?? join(pkgDir, "build"));
  await bundle({ outDir });
  console.log(`Monocle plugin bundled to ${outDir}`);
}
