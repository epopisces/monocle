import { createInterface } from "node:readline";
import type { Readable, Writable } from "node:stream";
import { fileURLToPath } from "node:url";
import { VAULT_TOOLS, callVaultTool } from "./tools.js";
import type { VaultReader } from "./vault-reader.js";

/** MCP server name Cravat registers the vault tools under; the Copilot CLI exposes them as `monocle_vault-<tool>`. */
export const VAULT_MCP_SERVER_NAME = "monocle_vault";

/**
 * Built stdio entry point (`node <entry> --vault <root> [--exclude <path>]…`). Resolved against the package's
 * `dist` so it also works when this module is loaded from source (tests); requires a build.
 */
export const VAULT_MCP_STDIO_ENTRY = fileURLToPath(new URL("../../dist/vault-tools/mcp-stdio.js", import.meta.url));

const SUPPORTED_PROTOCOLS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"];

interface JsonRpcMessage {
  jsonrpc?: string;
  id?: string | number | null;
  method?: string;
  params?: Record<string, unknown>;
}

/**
 * Serves the read-only vault tools over MCP's stdio transport (newline-delimited JSON-RPC 2.0). Resolves when
 * `input` ends.
 */
export async function serveVaultTools(reader: VaultReader, input: Readable, output: Writable): Promise<void> {
  const send = (msg: unknown) => output.write(`${JSON.stringify(msg)}\n`);
  const reply = (id: JsonRpcMessage["id"], result: unknown) => send({ jsonrpc: "2.0", id, result });
  const error = (id: JsonRpcMessage["id"], code: number, message: string) => send({ jsonrpc: "2.0", id: id ?? null, error: { code, message } });

  for await (const line of createInterface({ input, crlfDelay: Infinity })) {
    if (!line.trim()) continue;
    let msg: JsonRpcMessage;
    try {
      msg = JSON.parse(line) as JsonRpcMessage;
    } catch {
      error(null, -32700, "parse error");
      continue;
    }
    const isRequest = msg.id !== undefined && msg.id !== null;
    switch (msg.method) {
      case "initialize": {
        const requested = msg.params?.protocolVersion;
        reply(msg.id, {
          protocolVersion: typeof requested === "string" && SUPPORTED_PROTOCOLS.includes(requested) ? requested : SUPPORTED_PROTOCOLS[0],
          capabilities: { tools: { listChanged: false } },
          serverInfo: { name: VAULT_MCP_SERVER_NAME, version: "0.1.0" },
          instructions: "Read-only access to the user's Obsidian vault. Tools cannot modify notes.",
        });
        break;
      }
      case "ping":
        reply(msg.id, {});
        break;
      case "tools/list":
        reply(msg.id, { tools: VAULT_TOOLS });
        break;
      case "tools/call": {
        const name = msg.params?.name;
        const args = msg.params?.arguments;
        if (typeof name !== "string") {
          error(msg.id, -32602, "tools/call requires a tool name");
          break;
        }
        reply(msg.id, callVaultTool(reader, name, typeof args === "object" && args !== null ? (args as Record<string, unknown>) : {}));
        break;
      }
      default:
        if (isRequest) error(msg.id, -32601, `method not found: ${msg.method}`);
    }
  }
}
