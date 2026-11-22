import { Modal, Notice, requestUrl, setIcon, type App, type Plugin } from "obsidian";
import type { IndexHealth, IndexHealthLevel } from "@monocle/contracts";
import type { CompanionRequest, IndexHealthMonitor, IndexView } from "./index-health.js";

export const requestUrlCompanion: CompanionRequest = async ({ url, method, body }) => {
  const res = await requestUrl({
    url,
    method,
    throw: false,
    ...(body !== undefined && { body: JSON.stringify(body), contentType: "application/json" }),
  });
  let json: unknown;
  try {
    json = res.json;
  } catch {
    json = undefined;
  }
  return { status: res.status, json };
};

const ICONS: Record<IndexHealthLevel, string> = {
  healthy: "check-circle",
  indexing: "loader",
  degraded: "alert-triangle",
  unavailable: "circle-off",
};

const ago = (iso: string | null): string => {
  if (!iso) return "never";
  const s = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 1000));
  return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : new Date(iso).toLocaleString();
};

/**
 * Compact status-bar indicator plus commands. The expanded view is a modal, so when closed it occupies
 * no workspace space.
 */
export function installIndexHealthUi(plugin: Plugin, monitor: IndexHealthMonitor): void {
  const item = plugin.addStatusBarItem();
  item.addClass("monocle-index-indicator", "mod-clickable");
  const icon = item.createSpan({ cls: "monocle-index-icon" });
  const text = item.createSpan({ cls: "monocle-index-label" });
  const open = () => new IndexHealthModal(plugin.app, monitor).open();
  item.addEventListener("click", open);
  const unsubscribe = monitor.onChange((view) => {
    item.dataset.level = view.level;
    setIcon(icon, ICONS[view.level]);
    text.setText(view.label);
    item.setAttribute("aria-label", `Monocle: ${view.detail}`);
  });
  plugin.register(unsubscribe);

  const notify = async (action: Promise<{ ok: boolean; message: string }>) => {
    const result = await action;
    new Notice(result.ok ? result.message : `Monocle: ${result.message}`);
  };
  plugin.addCommand({ id: "show-index-health", name: "Show index health", callback: open });
  plugin.addCommand({ id: "reconcile-index", name: "Reconcile index", callback: () => void notify(monitor.reconcile()) });
  plugin.addCommand({
    id: "reindex-current-note",
    name: "Reindex current note",
    checkCallback: (checking) => {
      const file = plugin.app.workspace.getActiveFile();
      if (!file || file.extension !== "md") return false;
      if (!checking) void notify(monitor.reindexNote(file.path));
      return true;
    },
  });
  plugin.addCommand({
    id: "rebuild-indexes",
    name: "Rebuild all indexes",
    callback: () => confirmRebuild(plugin.app, () => void notify(monitor.rebuild())),
  });
}

function confirmRebuild(app: App, onConfirm: () => void): void {
  const modal = new Modal(app);
  modal.setTitle("Rebuild all Monocle indexes?");
  modal.contentEl.createEl("p", {
    text: "Discards the derived search, link and semantic indexes on this machine and rebuilds them from your Markdown. Notes are not changed. Semantic re-embedding may take a while.",
  });
  const buttons = modal.contentEl.createDiv({ cls: "modal-button-container" });
  buttons.createEl("button", { text: "Rebuild", cls: "mod-warning" }).addEventListener("click", () => {
    modal.close();
    onConfirm();
  });
  buttons.createEl("button", { text: "Cancel" }).addEventListener("click", () => modal.close());
  modal.open();
}

class IndexHealthModal extends Modal {
  private unsubscribe: (() => void) | undefined;
  private busy = false;

  constructor(
    app: App,
    private readonly monitor: IndexHealthMonitor,
  ) {
    super(app);
  }

  override onOpen(): void {
    this.setTitle("Monocle index health");
    this.modalEl.addClass("monocle-index-modal");
    const body = this.contentEl.createDiv();
    const actions = this.contentEl.createDiv({ cls: "monocle-index-actions" });
    const status = this.contentEl.createDiv({ cls: "monocle-index-action-status" });

    const run = async (action: () => Promise<{ ok: boolean; message: string }>) => {
      if (this.busy) return;
      this.busy = true;
      status.setText("Working…");
      const result = await action();
      this.busy = false;
      status.setText(result.message);
      status.toggleClass("mod-error", !result.ok);
    };
    const file = this.app.workspace.getActiveFile();
    const button = (label: string, onClick: () => void, cls?: string) =>
      actions.createEl("button", { text: label, ...(cls && { cls }) }).addEventListener("click", onClick);
    if (file?.extension === "md") button("Reindex current note", () => void run(() => this.monitor.reindexNote(file.path)));
    button("Reconcile", () => void run(() => this.monitor.reconcile()));
    button("Rebuild…", () => confirmRebuild(this.app, () => void run(() => this.monitor.rebuild())), "mod-warning");
    button("Refresh", () => void this.monitor.refresh());

    this.unsubscribe = this.monitor.onChange((view) => renderHealth(body, view));
    void this.monitor.refresh();
  }

  override onClose(): void {
    this.unsubscribe?.();
    this.contentEl.empty();
  }
}

function renderHealth(el: HTMLElement, view: IndexView): void {
  const warningsOpen = el.querySelector("details")?.open ?? false;
  el.empty();
  const head = el.createDiv({ cls: "monocle-index-head" });
  head.dataset.level = view.level;
  setIcon(head.createSpan({ cls: "monocle-index-icon" }), ICONS[view.level]);
  head.createSpan({ cls: "monocle-index-level", text: view.label });
  el.createDiv({ cls: "monocle-index-detail", text: view.detail });
  const h: IndexHealth | undefined = view.health;
  if (!h) return;

  const rows: [string, string][] = [
    ["Notes indexed", String(h.lexical.notes)],
    ["Last reconciled", ago(h.lexical.lastReconciledAt)],
    ["Broken links", String(h.lexical.brokenLinks)],
    ["Semantic", h.semantic.state === "disabled" ? "disabled (lexical only)" : `${h.semantic.state} · ${h.semantic.providerId ?? ""}`],
  ];
  if (h.semantic.state !== "disabled") {
    rows.push(
      ["Semantic queue", `${h.semantic.pendingNotes} notes${h.semantic.fullResyncPending ? " + full resync" : ""}`],
      ["Semantic coverage", `${h.semantic.indexedNotes} notes · ${h.semantic.indexedPassages} passages`],
      ["Last embedded", ago(h.semantic.lastIndexedAt)],
    );
    if (h.semantic.rebuildReason) rows.push(["Rebuilding", h.semantic.rebuildReason]);
  }
  const table = el.createEl("table", { cls: "monocle-index-table" });
  for (const [k, v] of rows) {
    const tr = table.createEl("tr");
    tr.createEl("th", { text: k });
    tr.createEl("td", { text: v });
  }

  if (h.errors.length) {
    el.createEl("h4", { text: `Errors (${h.errors.length})` });
    const list = el.createEl("ul", { cls: "monocle-index-errors" });
    for (const e of h.errors) list.createEl("li", { text: `[${e.source}] ${e.message} · ${ago(e.at)}` });
  }
  if (h.warnings.length) {
    const details = el.createEl("details", { cls: "monocle-index-warnings" });
    details.open = warningsOpen;
    details.createEl("summary", { text: `Vault warnings (${h.warnings.length})` });
    const list = details.createEl("ul");
    for (const w of h.warnings) list.createEl("li", { text: `${w.message}: ${w.paths.join(", ")}` });
  }
}
