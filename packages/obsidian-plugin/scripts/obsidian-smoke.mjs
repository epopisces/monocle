// Isolated Obsidian smoke test (IMM-46 connection, IMM-47 execution stream/cancel). Uses a temp copy of the fixture
// vault and a temp Electron user-data dir, so the user's Obsidian configuration and vaults are never touched.
// The companion runs Cravat against a fake Copilot CLI unless MONOCLE_SMOKE_LIVE=1 (uses the installed, signed-in
// Copilot CLI; costs one premium request; skips the cancel checks).
// Usage (from repo root, after `npm run build`): node <this file>
import { spawn, execFileSync } from "node:child_process";
import { cpSync, mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";

const repo = process.cwd();
const obsidianExe = process.env.OBSIDIAN_EXE ?? join(process.env.LOCALAPPDATA ?? "", "Programs", "Obsidian", "Obsidian.exe");
const work = mkdtempSync(join(tmpdir(), "monocle-obsidian-smoke-"));
const vault = join(work, "vault");
const userData = join(work, "userdata");
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
  const c = await startCompanion({ adapter });
  console.log(JSON.stringify({ event: "listening", url: c.url, instanceId: c.health.instanceId }));
`;

function startCompanion() {
  const args = live ? [join(repo, "packages/companion/dist/cli.js")] : ["--input-type=module", "-e", fakeLauncher];
  const child = spawn(process.execPath, args, { stdio: ["ignore", "pipe", "inherit"] });
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
const check = (name, ok, detail = "") => { results.push({ name, ok }); log(ok ? "PASS" : "FAIL", name, detail); };
let companion, obsidian;
try {
  companion = await startCompanion();
  log("companion", companion.url);
  obsidian = spawn(obsidianExe, [`--user-data-dir=${userData}`, `--remote-debugging-port=${cdpPort}`], { stdio: "ignore" });
  const { ws, evaluate } = await cdp();
  await until(evaluate, "!!(window.app && app.workspace && app.workspace.layoutReady)", true, 60000);
  await evaluate("(async () => { await app.plugins.setEnable(true); await app.plugins.enablePluginAndSave('monocle'); })()");
  check("plugin loads", await until(evaluate, "!!app.plugins.plugins.monocle", true));
  await evaluate("app.commands.executeCommandById('monocle:open-panel')");
  const label = "document.querySelector('.monocle-status-label')?.textContent";
  check("panel shows Connected", (await until(evaluate, label, "Connected")) === "Connected");
  const status = await evaluate("[...document.querySelectorAll('.status-bar-item')].map(e=>e.textContent).find(t=>t.startsWith('Monocle'))");
  check("status bar shows connected", status === "Monocle: Connected", status);

  // IMM-47: submit a prompt, observe the stream and execution identity, then cancel a long-running one.
  const q = (sel) => `document.querySelector('.monocle-panel ${sel}')`;
  const submit = (text) =>
    evaluate(`(() => { const p = ${q(".monocle-prompt")}; p.value = ${JSON.stringify(text)}; ${q(".monocle-send")}.click(); })()`);
  const outputState = `${q(".monocle-output")}?.dataset.state`;
  await submit(live ? "Reply with exactly: monocle smoke ok" : "hello from obsidian");
  check("prompt completes", (await until(evaluate, outputState, "completed", live ? 120000 : 20000)) === "completed");
  const answer = await evaluate(`${q(".monocle-output")}.textContent`);
  check("streamed answer shown", live ? /monocle smoke ok/i.test(answer) : answer.includes("echo: hello from obsidian"), answer);
  const meta = await evaluate(`${q(".monocle-execution")}.textContent`);
  check("execution ID shown", /^Execution [0-9a-f-]{36} · completed$/.test(meta), meta);

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
  const err = await evaluate("document.querySelector('.monocle-status-error')?.textContent");
  check("disconnected error visible", !!err, err);
  await evaluate("app.workspace.openLinkText('Ada Example', '', false)");
  const editorOk = await until(evaluate, "app.workspace.getActiveFile()?.basename === 'Ada Example' && !!app.workspace.activeEditor?.editor", true);
  check("native editor usable while disconnected", editorOk === true);

  companion = await startCompanion();
  check("panel reconnects after companion restart", (await until(evaluate, label, "Connected")) === "Connected");

  ws.close();
  obsidian.kill();
  await new Promise((r) => (obsidian.exitCode !== null ? r() : obsidian.once("exit", r)));
  await sleep(1000);
  const h = await (await fetch(new URL("/v1/health", companion.url))).json();
  check("companion still healthy after Obsidian closes", h.status === "ok" && h.instanceId === companion.instanceId);
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
