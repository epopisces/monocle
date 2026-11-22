import { request } from "node:http";
import { afterEach, describe, expect, it } from "vitest";
import { CONTRACT_VERSION, HEALTH_PATH, COMPANION_SERVICE_ID } from "@monocle/contracts";
import { startCompanion, type RunningCompanion } from "@monocle/companion";

let running: RunningCompanion | undefined;
afterEach(async () => {
  await running?.close();
  running = undefined;
});

function get(url: string, headers: Record<string, string> = {}): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const req = request(url, { headers }, (res) => {
      let body = "";
      res.setEncoding("utf8");
      res.on("data", (c: string) => (body += c));
      res.on("end", () => resolve({ status: res.statusCode ?? 0, body }));
    });
    req.on("error", reject);
    req.end();
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
