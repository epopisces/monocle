import { afterEach, describe, expect, it } from "vitest";
import { COMPANION_SERVICE_ID } from "@monocle/contracts";
import { startCompanion, type RunningCompanion } from "@monocle/companion";
import { CompanionConnection, type ConnectionState, type HealthProbe } from "@monocle/obsidian-plugin";

/** Stand-in for Obsidian's `requestUrl` adapter used by the real plugin. */
const fetchProbe: HealthProbe = async (url) => {
  const res = await fetch(url);
  return { status: res.status, json: (await res.json()) as unknown };
};

let companion: RunningCompanion | undefined;
let connection: CompanionConnection | undefined;
afterEach(async () => {
  connection?.stop();
  await companion?.close();
  companion = connection = undefined;
});

async function waitFor(conn: CompanionConnection, kind: ConnectionState["kind"]): Promise<ConnectionState> {
  for (let i = 0; i < 200; i++) {
    if (conn.state.kind === kind) return conn.state;
    await new Promise((r) => setTimeout(r, 10));
  }
  throw new Error(`timed out waiting for ${kind}; last state ${conn.state.kind}`);
}

describe("Obsidian plugin ↔ companion", () => {
  it("connects to a running companion", async () => {
    companion = await startCompanion({ port: 0 });
    connection = new CompanionConnection({ endpoint: companion.url, probe: fetchProbe });
    const state = await connection.check();
    expect(state.kind).toBe("connected");
    expect(state.kind === "connected" && state.health.instanceId).toBe(companion.health.instanceId);
  });

  it("shows disconnected when the companion stops and reconnects when it restarts", async () => {
    companion = await startCompanion({ port: 0 });
    const port = Number(new URL(companion.url).port);
    connection = new CompanionConnection({ endpoint: companion.url, probe: fetchProbe, intervalMs: 20 });
    const seen: string[] = [];
    connection.onChange((s) => seen.push(s.kind));
    connection.start();
    await waitFor(connection, "connected");

    await companion.close();
    const down = await waitFor(connection, "disconnected");
    expect(down.kind === "disconnected" && down.error).toBeTruthy();

    companion = await startCompanion({ port });
    const up = await waitFor(connection, "connected");
    expect(up.kind === "connected" && up.health.instanceId).toBe(companion.health.instanceId);
    expect(seen).toEqual(["connecting", "connected", "disconnected", "connected"]);
  });

  it("leaves the companion running when the plugin disconnects (Obsidian closing)", async () => {
    companion = await startCompanion({ port: 0 });
    connection = new CompanionConnection({ endpoint: companion.url, probe: fetchProbe, intervalMs: 20 });
    connection.start();
    await waitFor(connection, "connected");
    connection.stop();

    const again = new CompanionConnection({ endpoint: companion.url, probe: fetchProbe });
    expect((await again.check()).kind).toBe("connected");
  });

  it("reports an incompatible companion contract version", async () => {
    const probe: HealthProbe = async () => ({
      status: 200,
      json: { service: COMPANION_SERVICE_ID, status: "ok", contractVersion: "9.0.0", instanceId: "x", startedAt: "t" },
    });
    connection = new CompanionConnection({ endpoint: "http://127.0.0.1:1", probe });
    const state = await connection.check();
    expect(state.kind).toBe("incompatible");
    expect(state.kind === "incompatible" && state.error).toMatch(/9\.0\.0/);
  });

  it("treats a non-Monocle service on the endpoint as disconnected", async () => {
    const probe: HealthProbe = async () => ({ status: 200, json: { hello: "world" } });
    connection = new CompanionConnection({ endpoint: "http://127.0.0.1:1", probe });
    const state = await connection.check();
    expect(state.kind === "disconnected" && state.error).toMatch(/not a Monocle companion/);
  });

  it("times out a hung health check", async () => {
    const probe: HealthProbe = () => new Promise(() => {});
    connection = new CompanionConnection({ endpoint: "http://127.0.0.1:1", probe, timeoutMs: 30 });
    const state = await connection.check();
    expect(state.kind === "disconnected" && state.error).toMatch(/timed out/);
  });
});
