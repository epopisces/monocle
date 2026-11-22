#!/usr/bin/env node
// Stand-in for the Copilot CLI's `--output-format json --stream on` mode, so adapter tests need no credentials.
// Behaviour is selected by FAKE_COPILOT_MODE: stream | args | fail | result-error | hang. Without it, a prompt
// containing "[hang]" hangs, "[args]" echoes the CLI arguments and anything else streams (used by the Obsidian
// smoke test). `--help` / `help config` print help excerpts used for capability discovery.
// Like the real CLI, `--resume=<id>` fails fast when <id> starts with "missing"; `result.sessionId` echoes the
// `--session-id`/`--resume` value, and in stream mode a prompt containing "[session]" is answered with that ID.
import { stdin } from "node:process";

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

const mode = process.env.FAKE_COPILOT_MODE ?? (prompt.includes("[hang]") ? "hang" : prompt.includes("[args]") ? "args" : "stream");
const emit = (obj) => process.stdout.write(`${JSON.stringify(obj)}\n`);
const delta = (messageId, deltaContent) =>
  emit({ type: "assistant.message_delta", data: { messageId, deltaContent }, ephemeral: true });

emit({ type: "session.tools_updated", data: { model: "fake-model" }, ephemeral: true });
process.stdout.write("not json noise\n");

switch (mode) {
  case "stream":
    if (prompt.includes("[session]")) {
      delta("m1", `session: ${sessionId}`);
      emit({ type: "result", exitCode: 0, sessionId });
      break;
    }
    delta("m1", "echo: ");
    delta("m1", prompt);
    emit({ type: "assistant.message", data: { messageId: "m1", content: `echo: ${prompt}` } });
    emit({ type: "result", exitCode: 0, sessionId });
    break;
  case "args":
    delta("m1", JSON.stringify({ args: process.argv.slice(2), cwd: process.cwd() }));
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
