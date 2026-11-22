import { cpSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { request } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import {
  CONTRACT_VERSION,
  HEALTH_PATH,
  COMPANION_SERVICE_ID,
  INDEX_HEALTH_PATH,
  INDEX_REBUILD_PATH,
  INDEX_RECONCILE_PATH,
  INDEX_REINDEX_NOTE_PATH,
} from "@monocle/contracts";
import { openIndexService, type IndexService } from "@monocle/core";
import { startCompanion, type RunningCompanion } from "@monocle/companion";

let running: RunningCompanion | undefined;
let index: IndexService | undefined;
let work: string | undefined;
afterEach(async () => {
  await running?.close();
  running = undefined;
  index?.close();
  index = undefined;
  if (work) rmSync(work, { recursive: true, force: true });
  work = undefined;
});

function get(url: string, headers: Record<string, string> = {}): Promise<{ status: number; body: string }> {
  return send("GET", url, undefined, headers);
}

function post(url: string, body?: unknown, headers: Record<string, string> = { "content-type": "application/json" }) {
  return send("POST", url, body === undefined ? "" : JSON.stringify(body), headers);
}

function send(
  method: string,
  url: string,
  body: string | undefined,
  headers: Record<string, string>,
): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const req = request(url, { method, headers }, (res) => {
      let body = "";
      res.setEncoding("utf8");
      res.on("data", (c: string) => (body += c));
      res.on("end", () => resolve({ status: res.statusCode ?? 0, body }));
    });
    req.on("error", reject);
    req.end(body);
  });
}

describe("companion loopback endpoint", () => {
  it("reports health with its service identity and contract version", async () => {
    running = await startCompanion({ port: 0 });
    const res = await get(new URL(HEALTH_PATH, running.url).href);
    expect(res.status).toBe(200);
    expect(JSON.parse(res.body)).toMatchObject({
      service: COMPANION_SERVICE_ID,
      status: "ok",
      contractVersion: CONTRACT_VERSION,
    });
  });

  it("listens on the loopback interface only", async () => {
    running = await startCompanion({ port: 0 });
    expect(new URL(running.url).hostname).toBe("127.0.0.1");
  });

  it("refuses to bind a non-loopback host", async () => {
    await expect(startCompanion({ host: "0.0.0.0", port: 0 })).rejects.toThrow(/loopback/);
  });

  it("rejects requests whose Host header is not a loopback name", async () => {
    running = await startCompanion({ port: 0 });
    const res = await get(new URL(HEALTH_PATH, running.url).href, { Host: "evil.example:80" });
    expect(res.status).toBe(403);
  });

  it("returns 404 for unknown routes", async () => {
    running = await startCompanion({ port: 0 });
    expect((await get(new URL("/nope", running.url).href)).status).toBe(404);
  });
});

describe("companion index maintenance routes", () => {
  async function startWithIndex(): Promise<{ url: (p: string) => string; vault: string }> {
    work = mkdtempSync(join(tmpdir(), "monocle-companion-index-"));
    const vault = join(work, "vault");
    cpSync(fileURLToPath(new URL("../../../fixtures/vault/", import.meta.url)), vault, { recursive: true });
    index = openIndexService({ vaultRoot: vault, stateDir: join(work, "state"), excludeFolders: ["templates"], watch: false });
    running = await startCompanion({ port: 0, index });
    const base = running.url;
    return { url: (p) => new URL(p, base).href, vault };
  }

  it("serves index health", async () => {
    const { url } = await startWithIndex();
    const res = await get(url(INDEX_HEALTH_PATH));
    expect(res.status).toBe(200);
    expect(JSON.parse(res.body)).toMatchObject({ level: "healthy", lexical: { notes: 7 }, semantic: { state: "disabled" } });
  });

  it("reconciles, reindexes one note and rebuilds on request, returning changes and fresh health", async () => {
    const { url, vault } = await startWithIndex();
    writeFileSync(join(vault, "inbox/New.md"), "fresh\n");
    const reconciled = await post(url(INDEX_RECONCILE_PATH));
    expect(reconciled.status).toBe(200);
    expect(JSON.parse(reconciled.body)).toMatchObject({ changes: { added: 1 }, health: { lexical: { notes: 8 } } });

    writeFileSync(join(vault, "inbox/New.md"), "edited\n");
    const reindexed = await post(url(INDEX_REINDEX_NOTE_PATH), { path: "inbox/New.md" });
    expect(JSON.parse(reindexed.body)).toMatchObject({ changes: { updated: 1 } });

    const rebuilt = await post(url(INDEX_REBUILD_PATH));
    expect(JSON.parse(rebuilt.body)).toMatchObject({ changes: { added: 8 }, health: { level: "healthy" } });
  });

  it("rejects invalid reindex requests and non-JSON posts", async () => {
    const { url } = await startWithIndex();
    expect((await post(url(INDEX_REINDEX_NOTE_PATH), { path: "../secret.md" })).status).toBe(400);
    expect((await post(url(INDEX_REINDEX_NOTE_PATH), {})).status).toBe(400);
    // Browsers can send text/plain cross-origin without a CORS preflight; only JSON posts are accepted.
    expect((await post(url(INDEX_RECONCILE_PATH), undefined, { "content-type": "text/plain" })).status).toBe(415);
    expect((await get(url(INDEX_RECONCILE_PATH))).status).toBe(405);
  });

  it("reports 404 for index routes when the companion runs without a vault", async () => {
    running = await startCompanion({ port: 0 });
    expect((await get(new URL(INDEX_HEALTH_PATH, running.url).href)).status).toBe(404);
  });
});
