// Isolated Obsidian smoke test (IMM-46 connection, IMM-47 execution stream/cancel, IMM-48 note context
// and read-only vault tools, IMM-49 execution settings, IMM-50 conversations, IMM-51 command routing, IMM-61 index health). Uses a temp copy of the fixture vault, a temp Electron user-data dir and a
// temp companion data dir, so the user's Obsidian configuration, vaults and conversations are never touched. The
// companion runs Cravat against a fake Copilot CLI unless MONOCLE_SMOKE_LIVE=1 (uses the installed, signed-in
// Copilot CLI; costs three premium requests; skips the cancel checks).
// Usage (from repo root, after `npm run build`): node <this file>
import { spawn, execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, mkdtempSync, mkdirSync, readdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";

const repo = process.cwd();
const obsidianExe = process.env.OBSIDIAN_EXE ?? join(process.env.LOCALAPPDATA ?? "", "Programs", "Obsidian", "Obsidian.exe");
const work = mkdtempSync(join(tmpdir(), "monocle-obsidian-smoke-"));
const vault = join(work, "vault");
const userData = join(work, "userdata");
const dataDir = join(work, "companion-data");
const cdpPort = 9333;
const log = (...a) => console.log("[smoke]", ...a);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

cpSync(join(repo, "fixtures", "vault"), vault, { recursive: true });
execFileSync(process.execPath, [join(repo, "packages/obsidian-plugin/scripts/bundle.mjs"), "--vault", vault], { stdio: "inherit" });
mkdirSync(userData, { recursive: true });
writeFileSync(join(userData, "obsidian.json"), JSON.stringify({ vaults: { a1b2c3d4e5f60718: { path: vault, ts: Date.now(), open: true } } }));

const live = process.env.MONOCLE_SMOKE_LIVE === "1";
// Without MONOCLE_SMOKE_LIVE=1 the companion runs Cravat's Copilot adapter against a fake CLI (no credentials, no cost).
const fakeLauncher = `
  import { startCompanion } from ${JSON.stringify(new URL("packages/companion/dist/index.js", `file:///${repo.replace(/\\/g, "/")}/`).href)};
  import { CopilotCliAdapter } from ${JSON.stringify(new URL("packages/cravat/dist/index.js", `file:///${repo.replace(/\\/g, "/")}/`).href)};
  const adapter = new CopilotCliAdapter({ command: process.execPath, args: [${JSON.stringify(join(repo, "packages/cravat/test/fixtures/fake-copilot.mjs"))}] });
  const { openIndexService } = await import(${JSON.stringify(new URL("packages/monocle-core/dist/index.js", `file:///${repo.replace(/\\/g, "/")}/`).href)});
  const index = openIndexService({ vaultRoot: ${JSON.stringify(vault)}, stateDir: ${JSON.stringify(join(work, "state"))}, excludeFolders: ["templates"] });
  const c = await startCompanion({ adapter, index, dataDir: process.env.MONOCLE_DATA_DIR, vault: { root: ${JSON.stringify(vault)}, exclude: ["templates"] } });
  console.log(JSON.stringify({ event: "listening", url: c.url, instanceId: c.health.instanceId }));
`;

function startCompanion() {
  const indexArgs = ["--vault", vault, "--state-dir", join(work, "state"), "--exclude", "templates"];
  const args = live ? [join(repo, "packages/companion/dist/cli.js"), ...indexArgs] : ["--input-type=module", "-e", fakeLauncher];
  const child = spawn(process.execPath, args, {
    stdio: ["ignore", "pipe", "ignore"],
    env: { ...process.env, MONOCLE_DATA_DIR: dataDir },
  });
  return new Promise((resolve, reject) => {
    child.once("exit", (c) => reject(new Error(`companion exited ${c}`)));
    createInterface({ input: child.stdout }).on("line", (l) => {
      const m = JSON.parse(l);
      if (m.event === "listening") resolve({ child, url: m.url, instanceId: m.instanceId });
    });
  });
}

async function cdp() {
  for (let i = 0; i < 60; i++) {
    try {
      const targets = await (await fetch(`http://127.0.0.1:${cdpPort}/json`)).json();
      const page = targets.find((t) => t.type === "page");
      if (page) {
        const ws = new WebSocket(page.webSocketDebuggerUrl);
        await new Promise((r, j) => ((ws.onopen = r), (ws.onerror = j)));
        let id = 0;
        const pending = new Map();
        ws.onmessage = (e) => {
          const msg = JSON.parse(e.data);
          pending.get(msg.id)?.(msg);
          pending.delete(msg.id);
        };
        const evaluate = (expression) =>
          new Promise((resolve, reject) => {
            const n = ++id;
            pending.set(n, (m) => (m.result?.exceptionDetails ? reject(new Error(JSON.stringify(m.result.exceptionDetails))) : resolve(m.result?.result?.value)));
            ws.send(JSON.stringify({ id: n, method: "Runtime.evaluate", params: { expression, awaitPromise: true, returnByValue: true } }));
          });
        return { ws, evaluate };
      }
    } catch {}
    await sleep(500);
  }
  throw new Error("no CDP page target");
}

async function until(evaluate, expr, expected, timeoutMs = 20000) {
  const end = Date.now() + timeoutMs;
  let v;
  while (Date.now() < end) {
    try { v = await evaluate(expr); } catch {}
    if (v === expected) return v;
    await sleep(250);
  }
  throw new Error(`timeout waiting for ${expr} === ${expected}; last ${v}`);
}

const results = [];
/** Hashes of every note (Obsidian itself writes under .obsidian, so that is skipped). */
const noteHashes = () =>
  Object.fromEntries(
    readdirSync(vault, { recursive: true, withFileTypes: true })
      .filter((e) => e.isFile() && !join(e.parentPath, e.name).includes(".obsidian"))
      .map((e) => [join(e.parentPath, e.name), createHash("sha256").update(readFileSync(join(e.parentPath, e.name))).digest("hex")]),
  );
const check = (name, ok, detail = "") => { results.push({ name, ok }); log(ok ? "PASS" : "FAIL", name, detail); };
let companion, obsidian;
const launchObsidian = () =>
  spawn(obsidianExe, [`--user-data-dir=${userData}`, `--remote-debugging-port=${cdpPort}`], { stdio: "ignore" });
try {
  companion = await startCompanion();
  log("companion", companion.url);
  obsidian = launchObsidian();
  let { ws, evaluate } = await cdp();
  await until(evaluate, "!!(window.app && app.workspace && app.workspace.layoutReady)", true, 60000);
  await evaluate("(async () => { await app.plugins.setEnable(true); await app.plugins.enablePluginAndSave('monocle'); })()");
  check("plugin loads", await until(evaluate, "!!app.plugins.plugins.monocle", true));
  await evaluate("app.commands.executeCommandById('monocle:open-panel')");
  const label = "document.querySelector('.monocle-status-label')?.textContent";
  check("panel shows Connected", (await until(evaluate, label, "Connected")) === "Connected");
  const status = await evaluate("[...document.querySelectorAll('.status-bar-item')].map(e=>e.textContent).find(t=>t.startsWith('Monocle'))");
  check("status bar shows connected", status === "Monocle: Connected", status);

  const indexLabel = "document.querySelector('.monocle-index-indicator .monocle-index-label')?.textContent";
  check("index indicator shows healthy", (await until(evaluate, indexLabel, "Index healthy")) === "Index healthy");
  const leaves = "app.workspace.getLeavesOfType('monocle-panel').length + ':' + document.querySelectorAll('.workspace-leaf').length";
  const leavesBefore = await evaluate(leaves);
  await evaluate("document.querySelector('.monocle-index-indicator').click()");
  const modalText = "document.querySelector('.monocle-index-modal')?.textContent ?? ''";
  await until(evaluate, `(${modalText}).includes('Notes indexed')`, true);
  const modal = await evaluate(modalText);
  check("expanded panel shows freshness, queue and warnings", /Last reconciled/.test(modal) && /Semantic/.test(modal) && /Vault warnings/.test(modal), modal.slice(0, 200));
  await evaluate("[...document.querySelectorAll('.monocle-index-modal button')].find(b => b.textContent === 'Reconcile').click()");
  check("reconcile control runs", (await until(evaluate, "(document.querySelector('.monocle-index-action-status')?.textContent ?? '').startsWith('Reconciled:')", true)) === true);
  await evaluate("document.querySelector('.monocle-index-modal .modal-close-button').click()");
  await until(evaluate, "!document.querySelector('.monocle-index-modal')", true);
  check("closed panel occupies no workspace", (await evaluate(leaves)) === leavesBefore);

  await evaluate("app.workspace.openLinkText('Project Lantern', '', false)");
  await until(evaluate, "app.workspace.getActiveFile()?.basename === 'Project Lantern'", true);
  await evaluate("(async () => { const p = app.vault.adapter; await p.write('projects/Project Lantern.md', (await p.read('projects/Project Lantern.md')) + '\\nsmokeword-61\\n'); })()");
  await evaluate("app.commands.executeCommandById('monocle:reindex-current-note')");
  const notice = await until(evaluate, "[...document.querySelectorAll('.notice')].some(n => n.textContent.startsWith('Reindexed projects/Project Lantern.md'))", true).catch(() => false);
  check("reindex current note command", notice === true);

  // IMM-47: submit a prompt, observe the stream and execution identity, then cancel a long-running one.
  const q = (sel) => `document.querySelector('.monocle-panel ${sel}')`;
  const submit = (text) =>
    evaluate(`(() => { const p = ${q(".monocle-prompt")}; p.value = ${JSON.stringify(text)}; ${q(".monocle-send")}.click(); })()`);
  const outputState = `${q(".monocle-output")}?.dataset.state`;
  await submit(live ? "Reply with exactly: monocle smoke ok" : "hello from obsidian");
  check("prompt completes", (await until(evaluate, outputState, "completed", live ? 120000 : 20000)) === "completed");
  const answer = await evaluate(`${q(".monocle-output")}.textContent`);
  check("streamed answer shown", live ? /monocle smoke ok/i.test(answer) : answer.startsWith("echo: ") && answer.includes("hello from obsidian"), answer);
  const meta = await evaluate(`${q(".monocle-execution")}.textContent`);
  check("execution ID shown", /^Execution [0-9a-f-]{36} · completed$/.test(meta), meta);

  // IMM-50: a second prompt continues the same conversation and provider session; the first moves to the transcript.
  const storedConversation = "app.loadLocalStorage('monocle:conversation-id')";
  const conversationId = await evaluate(storedConversation);
  check("conversation ID remembered host-locally", /^[0-9a-f-]{36}$/.test(conversationId ?? ""), conversationId);
  await submit(live ? "What exact phrase did I ask you to reply with? Reply with only that phrase." : "second message");
  check("follow-up completes", (await until(evaluate, outputState, "completed", live ? 120000 : 20000)) === "completed");
  check("follow-up stays in the conversation", (await evaluate(storedConversation)) === conversationId);
  const session = await evaluate(`${q(".monocle-execution-session")}.textContent`);
  check("follow-up continues the provider session", session === "Continued provider session", session);
  if (live) {
    const recalled = await evaluate(`${q(".monocle-output")}.textContent`);
    check("provider remembers earlier context", /monocle smoke ok/i.test(recalled), recalled);
  }
  const turns = `${q(".monocle-transcript")}.querySelectorAll('.monocle-turn').length`;
  const transcriptText = `${q(".monocle-transcript")}.textContent`;
  check("earlier execution shown in transcript", (await until(evaluate, turns, 1)) === 1);
  const firstAnswer = live ? /monocle smoke ok/i : /echo: [\s\S]*hello from obsidian/;
  // IMM-49: provider-discovered settings, applied to the adapter request; unsupported values rejected visibly.
  const sel = (name) => q(`select[data-setting="${name}"]`);
  const pick = (name, value) =>
    evaluate(`(() => { const s = ${sel(name)}; if (![...s.options].some(o => o.value === ${JSON.stringify(value)})) s.add(new Option(${JSON.stringify(value)} + ' (unsupported)', ${JSON.stringify(value)})); s.value = ${JSON.stringify(value)}; s.dispatchEvent(new Event('change')); })()`);
  const optionsOf = (name) => evaluate(`[...(${sel(name)}?.options ?? [])].map(o => o.value).join(',')`);
  await until(evaluate, `!!${sel("model")}`, true);
  const models = await optionsOf("model");
  check("model choices discovered from the CLI", live ? models.split(",").length > 2 : models === ",auto,fake-pro,fake-mini", models);
  const efforts = await optionsOf("reasoningEffort");
  check("thinking effort choices shown", efforts.split(",").includes("low"), efforts);
  check("context window choices shown", (await optionsOf("contextWindow")).includes("long_context"));
  const failedState = `${q(".monocle-output")}?.dataset.state`;
  await pick("model", "no-such-model");
  await submit("rejected");
  await until(evaluate, failedState, "failed");
  const rejection = await evaluate(`${q(".monocle-execution-error")}.textContent`);
  check("unsupported setting reported, not ignored", /^invalid_request: model "no-such-model" is not supported/.test(rejection), rejection);
  await pick("model", live ? "" : "fake-pro");
  await pick("reasoningEffort", "low");
  if (!live) {
    await submit("show args [args]");
    await until(evaluate, outputState, "completed");
    const argsOut = await evaluate(`${q(".monocle-output")}.textContent`);
    check("chosen settings reach the Copilot CLI", argsOut.includes('"--model","fake-pro"') && argsOut.includes('"--reasoning-effort","low"'), argsOut);
  } else {
    await submit("Reply with exactly: monocle settings ok");
    check("live run with thinking effort low completes", (await until(evaluate, outputState, "completed", 120000)) === "completed");
  }
  await pick("model", "");
  await pick("reasoningEffort", "");

  if (!live) {
    await submit("long task [hang]");
    await until(evaluate, `${q(".monocle-output")}.textContent.startsWith('pid:')`, true);
    check("cancel enabled while running", (await evaluate(`${q(".monocle-cancel")}.disabled`)) === false);
    await evaluate(`${q(".monocle-cancel")}.click()`);
    check("cancel completes terminally", (await until(evaluate, outputState, "cancelled")) === "cancelled");
    const pid = Number((await evaluate(`${q(".monocle-output")}.textContent`)).replace("pid:", ""));
    await sleep(1000);
    let alive = true;
    try { process.kill(pid, 0); } catch { alive = false; }
    check("cancel stopped the provider process", !alive, `pid ${pid}`);
  }

  companion.child.kill();
  check("panel shows Disconnected after companion stops", (await until(evaluate, label, "Disconnected")) === "Disconnected");
  check("index indicator shows unavailable", (await until(evaluate, indexLabel, "Index unavailable")) === "Index unavailable");
  const err = await evaluate("document.querySelector('.monocle-status-error')?.textContent");
  check("disconnected error visible", !!err, err);
  await evaluate("app.workspace.openLinkText('Ada Example', '', false)");
  const editorOk = await until(evaluate, "app.workspace.getActiveFile()?.basename === 'Ada Example' && !!app.workspace.activeEditor?.editor", true);
  check("native editor usable while disconnected", editorOk === true);

  companion = await startCompanion();
  check("panel reconnects after companion restart", (await until(evaluate, label, "Connected")) === "Connected");
  await until(evaluate, `${firstAnswer}.test(${transcriptText})`, true);
  check("history survives a companion restart", true);

  // IMM-48: the active note (Ada Example, opened above) is sent as context, the agent reads another note via the
  // read-only vault tools, excluded notes stay out, and the vault is unchanged.
  const notesBefore = noteHashes();
  await evaluate(`(() => { ${q(".monocle-context-exclude")}.value = "work"; ${q(".monocle-context-include")}.value = "work/Duplicate Id Note.md"; })()`);
  await submit(
    live
      ? "Use your read_note tool to read projects/Project Lantern.md. Reply with the title of my active note and the unique search token from Project Lantern, nothing else."
      : '[tool:monocle_vault-read_note {"path":"projects/Project Lantern.md"}] [tool:monocle_vault-read_note {"path":"../outside.md"}] [tool:monocle_vault-read_note {"path":"work/Duplicate Id Note.md"}]',
  );
  check("context prompt completes", (await until(evaluate, outputState, "completed", live ? 180000 : 20000)) === "completed");
  const ctxAnswer = await evaluate(`${q(".monocle-output")}.textContent`);
  check("agent read another note through the vault tools", ctxAnswer.includes("lanternfish-7731"), ctxAnswer.slice(-300));
  if (live) {
    check("active note context used", /Ada Example/.test(ctxAnswer), ctxAnswer);
  } else {
    check("active note content sent", ctxAnswer.includes("Active note: people/Ada Example.md") && ctxAnswer.includes("Synthetic person"));
    check("excluded note not sent", !ctxAnswer.includes("Included note: work/Duplicate Id Note.md"));
    check("path traversal refused", /may not contain/.test(ctxAnswer));
    check("excluded note not readable by tools", /excluded from this request/.test(ctxAnswer));
  }
  check("vault notes unchanged", JSON.stringify(noteHashes()) === JSON.stringify(notesBefore));

  // IMM-51: one command registry across palette, context menus and chat. Deterministic commands run in Monocle
  // (no execution, no conversation entry); /lookup goes to Cravat; missing context is named.
  await evaluate(`(() => { ${q(".monocle-context-exclude")}.value = ""; ${q(".monocle-context-include")}.value = ""; })()`);
  const commandNotesBefore = noteHashes();
  const conversationCount = async () => {
    const { conversations } = await (await fetch(new URL("/v1/conversations", companion.url))).json();
    return conversations.reduce((n, c) => n + c.executionCount, 0) + ":" + conversations.length;
  };
  const executionsBefore = await conversationCount();
  const metaText = `${q(".monocle-execution")}?.textContent`;
  const outputText = `${q(".monocle-output")}.textContent`;
  await evaluate("app.workspace.openLinkText('Project Lantern', '', false)");
  await until(evaluate, "app.workspace.getActiveFile()?.basename === 'Project Lantern'", true);
  await evaluate("app.commands.executeCommandById('monocle:validate')");
  check("palette /validate runs in Monocle", (await until(evaluate, metaText, "Monocle /validate · completed")) === "Monocle /validate · completed");
  const validation = await evaluate(outputText);
  check("validation names the duplicate ID and broken link", validation.includes("work/Duplicate Id Note.md") && validation.includes("Missing Note"), validation);
  await submit("/search lanternfish-7731");
  await until(evaluate, metaText, "Monocle /search · completed");
  check("chat /search finds the note", (await evaluate(outputText)).includes("Project Lantern"));
  await submit("/backlinks");
  await until(evaluate, metaText, "Monocle /backlinks · completed");
  check("chat /backlinks lists linking notes", (await evaluate(outputText)).includes("Ada Example"));
  await submit("/valdiate");
  await until(evaluate, outputState, "failed");
  const unknown = await evaluate(`${q(".monocle-execution-error")}.textContent`);
  check("unknown chat command rejected locally", /^unknown_command: Unknown command \/valdiate\. Available commands: .*\/validate/.test(unknown), unknown);
  // A chainable stand-in for Obsidian's Menu collects the items every plugin adds for the file.
  const fileMenuValidate = `(() => {
    const items = [];
    const chain = (target) => new Proxy(target, { get: (t, p) => (p in t ? t[p] : (...a) => { if (p === "setTitle") t.title = a[0]; if (p === "onClick") t.click = a[0]; return chain(t); }) });
    const menu = chain({ addItem(cb) { const item = {}; items.push(item); cb(chain(item)); return menu; } });
    app.workspace.trigger("file-menu", menu, app.vault.getAbstractFileByPath("work/Duplicate Id Note.md"), "file-explorer-context-menu");
    const item = items.find((i) => i.title === "Monocle: Validate note");
    if (!item) return items.map((i) => i.title).join("|");
    item.click();
    return "clicked";
  })()`;
  const menuResult = await evaluate(fileMenuValidate);
  check("file menu offers Monocle commands", menuResult === "clicked", menuResult);
  await until(evaluate, metaText, "Monocle /validate · completed");
  check("file menu /validate targets that file", (await evaluate(outputText)).includes("projects/Project Lantern.md"));
  check("deterministic commands started no Cravat execution", (await conversationCount()) === executionsBefore);
  await evaluate("app.workspace.getLeavesOfType('markdown').forEach((l) => l.detach())");
  await evaluate("app.commands.executeCommandById('monocle:validate')");
  await until(evaluate, outputState, "failed");
  const missing = await evaluate(`${q(".monocle-execution-error")}.textContent`);
  check("missing active note named", /^missing_context: \/validate needs an active note/.test(missing), missing);
  await submit(live ? "/lookup Who owns Project Lantern? Reply in one sentence." : "/lookup Who owns Project Lantern?");
  check("chat /lookup completes in Cravat", (await until(evaluate, outputState, "completed", live ? 180000 : 20000)) === "completed");
  const lookup = await evaluate(outputText);
  if (live) check("lookup answers from the vault", /Ada Example/.test(lookup), lookup);
  else check("lookup sends grounding instructions", lookup.startsWith("echo: ") && lookup.includes("monocle_vault") && lookup.includes("Question: Who owns Project Lantern?"), lookup.slice(0, 300));
  check("lookup ran as an execution", /^Execution [0-9a-f-]{36} · completed$/.test(await evaluate(metaText)));
  check("vault notes unchanged by commands", JSON.stringify(noteHashes()) === JSON.stringify(commandNotesBefore));

  ws.close();
  obsidian.kill();
  await new Promise((r) => (obsidian.exitCode !== null ? r() : obsidian.once("exit", r)));
  await sleep(1000);
  const h = await (await fetch(new URL("/v1/health", companion.url))).json();
  check("companion still healthy after Obsidian closes", h.status === "ok" && h.instanceId === companion.instanceId);

  // Reopen Obsidian with the same profile: the panel restores the open conversation from the companion.
  obsidian = launchObsidian();
  ({ ws, evaluate } = await cdp());
  await until(evaluate, "!!(window.app && app.workspace && app.workspace.layoutReady && app.plugins.plugins.monocle)", true, 60000);
  await evaluate("app.commands.executeCommandById('monocle:open-panel')");
  await until(evaluate, label, "Connected");
  check("conversation restored after Obsidian restart", (await until(evaluate, `${q(".monocle-conversation-select")}?.value`, conversationId)) === conversationId);
  await until(evaluate, `${q(".monocle-transcript")}.querySelectorAll('.monocle-turn').length >= 2 && ${firstAnswer}.test(${transcriptText})`, true);
  check("restored transcript shows earlier executions", true);
  ws.close();
} catch (e) {
  check("smoke run", false, e.message);
} finally {
  companion?.child.kill();
  obsidian?.kill();
  await sleep(1500);
  try { rmSync(work, { recursive: true, force: true }); } catch {}
}
const failed = results.filter((r) => !r.ok).length;
log(`${results.length - failed}/${results.length} passed`);
process.exit(failed ? 1 : 0);
