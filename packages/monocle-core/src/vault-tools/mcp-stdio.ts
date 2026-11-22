#!/usr/bin/env node
/**
 * Read-only Monocle vault tools as an MCP stdio server, spawned per execution by the agent runtime.
 * Usage: node mcp-stdio.js --vault <root> [--exclude <vault-relative note or folder>]…
 */
import { parseArgs } from "node:util";
import { serveVaultTools } from "./mcp-server.js";
import { VaultReader } from "./vault-reader.js";

const { values } = parseArgs({
  options: { vault: { type: "string" }, exclude: { type: "string", multiple: true } },
  strict: true,
});

if (!values.vault) {
  process.stderr.write("monocle vault MCP server: --vault <root> is required\n");
  process.exit(2);
}

const reader = new VaultReader({ vaultRoot: values.vault, exclude: values.exclude ?? [] });
await serveVaultTools(reader, process.stdin, process.stdout);
