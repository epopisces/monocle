#!/usr/bin/env node
/**
 * Standalone companion launcher. Runs independently of Obsidian; stop it with Ctrl+C / SIGTERM.
 * Options: --host <loopback> --port <n>, or MONOCLE_COMPANION_HOST / MONOCLE_COMPANION_PORT;
 * --vault <folder> (or MONOCLE_VAULT) lets the agent read that vault through read-only tools;
 * --exclude <vault-relative note or folder> (repeatable) keeps notes out of every execution.
 */
import { resolve } from "node:path";
import { parseArgs } from "node:util";
import { startCompanion } from "./server.js";

const { values } = parseArgs({
  options: {
    host: { type: "string" },
    port: { type: "string" },
    vault: { type: "string" },
    exclude: { type: "string", multiple: true },
  },
  strict: true,
});

const host = values.host ?? process.env.MONOCLE_COMPANION_HOST;
const vaultRoot = values.vault ?? process.env.MONOCLE_VAULT;
const vault = vaultRoot ? { root: resolve(vaultRoot), exclude: values.exclude ?? [] } : undefined;
const portText = values.port ?? process.env.MONOCLE_COMPANION_PORT;
const port = portText === undefined ? undefined : Number(portText);
if (port !== undefined && (!Number.isInteger(port) || port < 0 || port > 65535)) {
  console.error(`Invalid port: ${portText}`);
  process.exit(2);
}

try {
  const companion = await startCompanion({ ...(host && { host }), ...(port !== undefined && { port }), ...(vault && { vault }) });
  // One JSON line on stdout so supervisors and tests can discover the bound URL.
  console.log(JSON.stringify({ event: "listening", url: companion.url, instanceId: companion.health.instanceId }));
  const shutdown = () => void companion.close().then(() => process.exit(0));
  process.once("SIGINT", shutdown);
  process.once("SIGTERM", shutdown);
} catch (err) {
  console.error(`Monocle companion failed to start: ${(err as Error).message}`);
  process.exit(1);
}
