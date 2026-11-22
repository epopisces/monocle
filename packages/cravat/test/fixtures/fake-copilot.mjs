#!/usr/bin/env node
// Stand-in for the Copilot CLI's `--output-format json --stream on` mode, so adapter tests need no credentials.
// Behaviour is selected by FAKE_COPILOT_MODE: stream | args | fail | result-error | hang. Without it, a prompt
// containing "[hang]" hangs and anything else streams (used by the Obsidian smoke test).
// Like the real CLI, `--resume=<id>` fails fast when <id> starts with "missing"; `result.sessionId` echoes the
// `--session-id`/`--resume` value, and in stream mode a prompt containing "[session]" is answered with that ID.
import { argv, stdin } from "node:process";

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

const mode = process.env.FAKE_COPILOT_MODE ?? (prompt.includes("[hang]") ? "hang" : "stream");
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
