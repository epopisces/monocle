// Isolated Obsidian smoke test for IMM-46 (connection) and IMM-61 (index health). Uses a temp copy of the fixture vault and a temp Electron
// user-data dir, so the user's Obsidian configuration and vaults are never touched.
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

function startCompanion() {
  const args = ["--vault", vault, "--state-dir", join(work, "state"), "--exclude", "templates"];
  const child = spawn(process.execPath, [join(repo, "packages/companion/dist/cli.js"), ...args], { stdio: ["ignore", "pipe", "ignore"] });
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
