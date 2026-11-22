#!/usr/bin/env node
/**
 * Standalone companion launcher. Runs independently of Obsidian; stop it with Ctrl+C / SIGTERM.
 * Options: --host <loopback> --port <n> --data-dir <path>, or MONOCLE_COMPANION_HOST / MONOCLE_COMPANION_PORT /
 * MONOCLE_DATA_DIR. The data dir holds machine-local state (conversations) and must not be inside a synced vault.
 */
import { homedir } from "node:os";
import { resolve } from "node:path";
import { parseArgs } from "node:util";
import { defaultDataDir } from "./data-dir.js";
import { startCompanion } from "./server.js";

const { values } = parseArgs({
  options: { host: { type: "string" }, port: { type: "string" }, "data-dir": { type: "string" } },
  strict: true,
});

const host = values.host ?? process.env.MONOCLE_COMPANION_HOST;
const dataDir = resolve(
  values["data-dir"] || process.env.MONOCLE_DATA_DIR || defaultDataDir(process.platform, process.env, homedir()),
);
const portText = values.port ?? process.env.MONOCLE_COMPANION_PORT;
const port = portText === undefined ? undefined : Number(portText);
if (port !== undefined && (!Number.isInteger(port) || port < 0 || port > 65535)) {
  console.error(`Invalid port: ${portText}`);
  process.exit(2);
}

try {
  const companion = await startCompanion({ ...(host && { host }), ...(port !== undefined && { port }), dataDir });
  // One JSON line on stdout so supervisors and tests can discover the bound URL.
  console.log(JSON.stringify({ event: "listening", url: companion.url, instanceId: companion.health.instanceId, dataDir }));
  const shutdown = () => void companion.close().then(() => process.exit(0));
  process.once("SIGINT", shutdown);
  process.once("SIGTERM", shutdown);
} catch (err) {
  console.error(`Monocle companion failed to start: ${(err as Error).message}`);
  process.exit(1);
}
