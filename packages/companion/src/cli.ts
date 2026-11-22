#!/usr/bin/env node
/**
 * Standalone companion launcher. Runs independently of Obsidian; stop it with Ctrl+C / SIGTERM.
 * Options: --host <loopback> --port <n> (or MONOCLE_COMPANION_HOST / MONOCLE_COMPANION_PORT);
 * --data-dir <dir> (or MONOCLE_DATA_DIR) holds machine-local conversations (never inside a synced vault; default
 * %LOCALAPPDATA%\Monocle, ~/Library/Application Support/Monocle or $XDG_STATE_HOME/monocle);
 * --vault <dir> (or MONOCLE_VAULT) enables the derived indexes and lets the agent read that vault through
 * read-only tools, with --state-dir <dir> (host-local, default ~/.monocle/state/<vault hash>), repeatable
 * --exclude <vault-relative folder or note> (not indexed, never sent to or readable by the agent), and
 * --semantic-config <json file>.
 * --note-template <name> enables /new-note (a template in the vault's Obsidian templates folder), with optional
 * --note-folder <vault-relative folder>, repeatable --note-field <key=value>, and --note-renderer <executable> plus
 * repeatable --note-renderer-arg <arg> to render through an external script (e.g. Curator's create-obsidian-note).
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { parseArgs } from "node:util";
import {
  commandNoteRenderer,
  createSemanticIndexFromConfig,
  openIndexService,
  type IndexService,
  type SemanticConfig,
} from "@monocle/core";
import type { CompanionNotesOptions } from "./command-routes.js";
import { defaultDataDir } from "./data-dir.js";
import { startCompanion } from "./server.js";

const { values } = parseArgs({
  options: {
    host: { type: "string" },
    port: { type: "string" },
    "data-dir": { type: "string" },
    vault: { type: "string" },
    "state-dir": { type: "string" },
    exclude: { type: "string", multiple: true },
    "semantic-config": { type: "string" },
    "note-template": { type: "string" },
    "note-folder": { type: "string" },
    "note-field": { type: "string", multiple: true },
    "note-renderer": { type: "string" },
    "note-renderer-arg": { type: "string", multiple: true },
  },
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

function noteOptions(): CompanionNotesOptions | undefined {
  const template = values["note-template"];
  if (!template) return undefined;
  const fields: Record<string, string> = {};
  for (const pair of values["note-field"] ?? []) {
    const eq = pair.indexOf("=");
    if (eq <= 0) {
      console.error(`Invalid --note-field ${pair}: expected key=value`);
      process.exit(2);
    }
    fields[pair.slice(0, eq)] = pair.slice(eq + 1);
  }
  const renderer = values["note-renderer"];
  return {
    template,
    fields,
    ...(values["note-folder"] !== undefined && { folder: values["note-folder"] }),
    ...(renderer && { renderer: commandNoteRenderer({ command: renderer, args: values["note-renderer-arg"] ?? [] }) }),
  };
}
const notes = noteOptions();

function openIndex(vaultArg: string): IndexService {
  const vaultRoot = resolve(vaultArg);
  const stateDir =
    values["state-dir"] ??
    join(homedir(), ".monocle", "state", createHash("sha256").update(vaultRoot).digest("hex").slice(0, 16));
  const semanticConfig = values["semantic-config"]
    ? (JSON.parse(readFileSync(values["semantic-config"], "utf8")) as SemanticConfig)
    : undefined;
  return openIndexService({
    vaultRoot,
    stateDir,
    ...(values.exclude && { excludeFolders: values.exclude }),
    semantic: (deps) => createSemanticIndexFromConfig(semanticConfig, deps),
  });
}

let index: IndexService | undefined;
try {
  const vault = values.vault ?? process.env.MONOCLE_VAULT;
  index = vault ? openIndex(vault) : undefined;
  const companion = await startCompanion({
    ...(host && { host }),
    ...(port !== undefined && { port }),
    ...(index && { index }),
    ...(vault && { vault: { root: resolve(vault), exclude: values.exclude ?? [] } }),
    ...(notes && { notes }),
    dataDir,
  });
  // One JSON line on stdout so supervisors and tests can discover the bound URL.
  console.log(JSON.stringify({ event: "listening", url: companion.url, instanceId: companion.health.instanceId, dataDir }));
  const shutdown = () =>
    void companion.close().then(() => {
      index?.close();
      process.exit(0);
    });
  process.once("SIGINT", shutdown);
  process.once("SIGTERM", shutdown);
} catch (err) {
  index?.close();
  console.error(`Monocle companion failed to start: ${(err as Error).message}`);
  process.exit(1);
}
