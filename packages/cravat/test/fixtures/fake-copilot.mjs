#!/usr/bin/env node
// Stand-in for the Copilot CLI's `--output-format json --stream on` mode, so adapter tests need no credentials.
// Behaviour is selected by FAKE_COPILOT_MODE: stream | args | fail | result-error | hang. Without it, a prompt
// containing "[hang]" hangs, "[args]" echoes the CLI arguments and anything else streams (used by the Obsidian
// smoke test). `--help` / `help config` print help excerpts used for capability discovery.
// Like the real CLI, `--resume=<id>` fails fast when <id> starts with "missing"; `result.sessionId` echoes the
// `--session-id`/`--resume` value, and in stream mode a prompt containing "[session]" is answered with that ID.
// In stream mode, each `[tool:<server>-<tool> {json args}]` in the prompt is "called" like the real CLI would:
// only if listed by --available-tools, via the stdio MCP server configured with --additional-mcp-config.
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { stdin } from "node:process";
import { createInterface } from "node:readline";

// Help output used for capability discovery (excerpts in the real CLI 1.0.104 format).
const argv = process.argv.slice(2);
if (argv.includes("--help")) {
  process.stdout.write(`Usage: copilot [OPTIONS] [COMMAND]

      --model <model>
          Set the AI model to use (use 'auto' to let Copilot pick
          automatically)
      --reasoning-effort <level>
          Set the reasoning effort level [possible values: low, medium, high]
      --context <tier>
          Set the context window tier (overrides persisted setting) [possible values: default, long_context]
`);
  process.exit(0);
}
if (argv[0] === "help" && argv[1] === "config") {
  process.stdout.write(`Configuration Settings:

  \`model\`: AI model to use for Copilot CLI; can be changed with /model command or --model flag option.
    - "fake-pro"
    - "fake-mini"

  \`contextTier\`: context window tier for tiered-pricing models (e.g., "default" or "long_context").
    - "not-a-model"
`);
  process.exit(0);
}

const flag = (name) => argv.find((a) => a.startsWith(`--${name}=`))?.slice(name.length + 3);
const resume = flag("resume");
if (resume?.startsWith("missing")) {
  process.stderr.write(`Error: No session, task, or name matched '${resume}'.\n\nTo resume by session or task ID:  copilot --resume=<id>\n`);
  process.exit(1);
}
const sessionId = resume ?? flag("session-id") ?? "fake-session";

let prompt = "";
stdin.setEncoding("utf8");
for await (const chunk of stdin) prompt += chunk;

const flagValues = (flag) => argv.flatMap((a, i) => (a === flag ? [argv[i + 1]] : []));
const available = new Set(flagValues("--available-tools").filter((t) => t !== "none"));
const mcpServers = Object.assign(
  {},
  ...flagValues("--additional-mcp-config").map((v) => JSON.parse(v.startsWith("@") ? readFileSync(v.slice(1), "utf8") : v).mcpServers),
);

const mode = process.env.FAKE_COPILOT_MODE ?? (prompt.includes("[hang]") ? "hang" : prompt.includes("[args]") ? "args" : "stream");
const emit = (obj) => process.stdout.write(`${JSON.stringify(obj)}\n`);
const delta = (messageId, deltaContent) =>
  emit({ type: "assistant.message_delta", data: { messageId, deltaContent }, ephemeral: true });

async function callTool(fullName, args) {
  if (!available.has(fullName)) return "unavailable";
  const serverName = Object.keys(mcpServers).find((s) => fullName.startsWith(`${s}-`));
  const server = mcpServers[serverName];
  const child = spawn(server.command, server.args ?? [], { env: { ...process.env, ...server.env }, stdio: ["pipe", "pipe", "inherit"] });
  const lines = createInterface({ input: child.stdout })[Symbol.asyncIterator]();
  const rpc = async (id, method, params) => {
    child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`);
    return JSON.parse((await lines.next()).value);
  };
  await rpc(1, "initialize", { protocolVersion: "2025-11-25", capabilities: {}, clientInfo: { name: "fake-copilot", version: "0" } });
  const res = await rpc(2, "tools/call", { name: fullName.slice(serverName.length + 1), arguments: args });
  child.kill();
  return res.result ? res.result.content.map((c) => c.text).join("\n") : `error: ${res.error?.message}`;
}

emit({ type: "session.tools_updated", data: { model: "fake-model" }, ephemeral: true });
process.stdout.write("not json noise\n");

switch (mode) {
  case "stream": {
    if (prompt.includes("[session]")) {
      delta("m1", `session: ${sessionId}`);
      emit({ type: "result", exitCode: 0, sessionId });
      break;
    }
    delta("m1", "echo: ");
    delta("m1", prompt);
    let toolText = "";
    for (const [, name, args] of prompt.matchAll(/\[tool:([\w-]+) (\{[^\]]*\})\]/g)) {
      toolText += `\n[${name}] ${await callTool(name, JSON.parse(args))}`;
    }
    if (toolText) delta("m1", toolText);
    emit({ type: "assistant.message", data: { messageId: "m1", content: `echo: ${prompt}${toolText}` } });
    emit({ type: "result", exitCode: 0, sessionId });
    break;
  }
  case "args":
    delta("m1", JSON.stringify({ args: argv, cwd: process.cwd(), mcpConfig: Object.keys(mcpServers).length ? { mcpServers } : undefined }));
    emit({ type: "result", exitCode: 0 });
    break;
  case "fail":
    process.stderr.write('Error: Model "nope" from --model flag is not available.\n');
    process.exit(1);
    break;
  case "result-error":
    emit({ type: "session.error", data: { message: "rate limited" } });
    emit({ type: "result", exitCode: 1 });
    process.exit(0);
    break;
  case "hang":
    delta("m1", `pid:${process.pid}`);
    setInterval(() => {}, 1_000);
    break;
}
