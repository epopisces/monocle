import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";
// @ts-expect-error -- plain ESM build script without type declarations
import { bundle } from "../scripts/bundle.mjs";

const out = mkdtempSync(join(tmpdir(), "monocle-plugin-"));
afterAll(() => rmSync(out, { recursive: true, force: true }));

describe("plugin bundle", () => {
  it("produces an installable Obsidian plugin that requires only the obsidian API at runtime", async () => {
    await (bundle as (o: { outDir: string }) => Promise<void>)({ outDir: out });

    const manifest = JSON.parse(readFileSync(join(out, "manifest.json"), "utf8")) as { id: string };
    expect(manifest.id).toBe("monocle");
    readFileSync(join(out, "styles.css"), "utf8");

    const required: string[] = [];
    const stub = class {};
    const fakeRequire = (id: string) => {
      required.push(id);
      return { Plugin: stub, ItemView: stub, PluginSettingTab: stub, Setting: stub, Modal: stub, Notice: stub, requestUrl: () => undefined };
    };
    const module = { exports: {} as { default?: { prototype: { onload?: unknown } } } };
    new Function("module", "exports", "require", readFileSync(join(out, "main.js"), "utf8"))(
      module,
      module.exports,
      fakeRequire,
    );

    expect(new Set(required)).toEqual(new Set(["obsidian"]));
    expect(typeof module.exports.default?.prototype.onload).toBe("function");
  }, 30_000);
});
