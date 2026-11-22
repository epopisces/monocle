import {
  ItemView,
  MarkdownRenderer,
  MarkdownView,
  Plugin,
  PluginSettingTab,
  Setting,
  requestUrl,
  type App,
  type WorkspaceLeaf,
} from "obsidian";
import {
  DEFAULT_COMPANION_ENDPOINT,
  EXECUTION_SETTING_NAMES,
  type ExecutionCapabilities,
  type ExecutionSettingName,
  type ExecutionSettings,
} from "@monocle/contracts";
import { CompanionConnection, type ConnectionState, type HealthProbe } from "./connection.js";
import { buildExecutionContext, type ActiveNoteSnapshot } from "./context.js";
import { parseCompanionEndpoint } from "./endpoint.js";
import { IndexHealthMonitor } from "./index-health.js";
import { installIndexHealthUi, requestUrlCompanion } from "./index-ui.js";
import { ExecutionClient, type ExecutionHandle, type FetchLike } from "./execution-client.js";

/**
 * Executions stream over the renderer's `fetch` (`requestUrl` buffers whole responses). The companion
 * allows Obsidian's `app://obsidian.md` origin via CORS and rejects every other browser origin.
 */
const rendererFetch: FetchLike = (input, init) => window.fetch(input, init);

const VIEW_TYPE = "monocle-panel";
/** Host-local (per vault, per machine) key; the endpoint must not sync through the vault (D01). */
const ENDPOINT_STORAGE_KEY = "monocle:companion-endpoint";
const SETTINGS_STORAGE_KEY = "monocle:execution-settings";

const SETTING_LABELS: Record<ExecutionSettingName, string> = {
  model: "Model",
  reasoningEffort: "Thinking effort",
  contextWindow: "Context window",
};

/**
 * Renders one select per setting the provider supports. A saved value the provider no longer offers stays
 * selected and marked unsupported, so the companion rejects it visibly instead of it being dropped silently.
 */
function renderSettings(container: HTMLElement, caps: ExecutionCapabilities | undefined, plugin: MonoclePlugin): void {
  container.empty();
  const saved = plugin.executionSettings();
  const names = EXECUTION_SETTING_NAMES.filter((n) => caps?.settings[n]);
  if (names.length === 0) {
    container.createDiv({ cls: "monocle-settings-none", text: "Provider exposes no execution settings." });
    return;
  }
  for (const name of names) {
    const options = caps!.settings[name]!.options;
    const field = container.createEl("label", { cls: "monocle-setting" });
    field.createSpan({ text: SETTING_LABELS[name] });
    const select = field.createEl("select", { cls: "dropdown", attr: { "data-setting": name } });
    select.createEl("option", { value: "", text: "Provider default" });
    for (const option of options) select.createEl("option", { value: option, text: option });
    const current = saved[name];
    if (current && !options.includes(current)) select.createEl("option", { value: current, text: `${current} (unsupported)` });
    select.value = current ?? "";
    select.addEventListener("change", () => plugin.setExecutionSetting(name, select.value || undefined));
  }
}

const requestUrlProbe: HealthProbe = async (url) => {
  const res = await requestUrl({ url, method: "GET", throw: false });
  let json: unknown;
  try {
    json = res.json;
  } catch {
    json = undefined;
  }
  return { status: res.status, json };
};

const LABELS: Record<ConnectionState["kind"], string> = {
  connecting: "Connecting…",
  connected: "Connected",
  disconnected: "Disconnected",
  incompatible: "Incompatible companion",
};

export default class MonoclePlugin extends Plugin {
  connection!: CompanionConnection;
  private readonly stateListeners = new Set<(s: ConnectionState) => void>();
  private unsubscribe: (() => void) | undefined;
  /** Focusing the Monocle panel clears the active view, so remember the last Markdown note the user was in. */
  private lastMarkdownView: MarkdownView | undefined;

  override async onload(): Promise<void> {
    const status = this.addStatusBarItem();
    this.stateListeners.add((s) => status.setText(`Monocle: ${LABELS[s.kind]}`));
    const indexMonitor = new IndexHealthMonitor({ request: requestUrlCompanion });
    this.register(() => indexMonitor.stop());
    this.stateListeners.add((s) => void indexMonitor.setConnection(s));
    installIndexHealthUi(this, indexMonitor);
    this.connect(this.storedEndpoint());

    this.lastMarkdownView = this.app.workspace.getActiveViewOfType(MarkdownView) ?? undefined;
    this.registerEvent(
      this.app.workspace.on("active-leaf-change", (leaf) => {
        if (leaf?.view instanceof MarkdownView) this.lastMarkdownView = leaf.view;
      }),
    );

    this.registerView(VIEW_TYPE, (leaf) => new MonoclePanelView(leaf, this));
    this.addRibbonIcon("glasses", "Open Monocle panel", () => void this.activatePanel());
    this.addCommand({ id: "open-panel", name: "Open panel", callback: () => void this.activatePanel() });
    this.addCommand({ id: "reconnect", name: "Reconnect to companion", callback: () => void this.connection.check() });
    this.addSettingTab(new MonocleSettingTab(this.app, this));
  }

  override onunload(): void {
    // Only stop observing: the companion keeps running when Obsidian closes.
    this.connection.stop();
    this.unsubscribe?.();
  }

  /** The last focused Markdown note (path, editor text and selection), if it is still open. */
  activeNoteSnapshot(): ActiveNoteSnapshot | undefined {
    const view = this.lastMarkdownView;
    if (!view?.file || !this.app.workspace.getLeavesOfType("markdown").some((l) => l.view === view)) return undefined;
    const selection = view.editor.getSelection();
    return { path: view.file.path, content: view.editor.getValue(), ...(selection && { selection }) };
  }

  storedEndpoint(): string {
    const saved: unknown = this.app.loadLocalStorage(ENDPOINT_STORAGE_KEY);
    const parsed = parseCompanionEndpoint(typeof saved === "string" ? saved : "");
    return parsed.ok ? parsed.endpoint : DEFAULT_COMPANION_ENDPOINT;
  }

  setEndpoint(endpoint: string): void {
    this.app.saveLocalStorage(ENDPOINT_STORAGE_KEY, endpoint === DEFAULT_COMPANION_ENDPOINT ? null : endpoint);
    this.connect(endpoint);
  }

  onState(listener: (s: ConnectionState) => void): () => void {
    this.stateListeners.add(listener);
    listener(this.connection.state);
    return () => this.stateListeners.delete(listener);
  }

  /** Execution settings chosen in the panel. Host-local: model availability differs per machine/account. */
  executionSettings(): ExecutionSettings {
    const saved: unknown = this.app.loadLocalStorage(SETTINGS_STORAGE_KEY);
    if (typeof saved !== "string") return {};
    try {
      const parsed = JSON.parse(saved) as Record<string, unknown>;
      const out: Partial<Record<ExecutionSettingName, string>> = {};
      for (const name of EXECUTION_SETTING_NAMES) {
        const v = parsed[name];
        if (typeof v === "string" && v) out[name] = v;
      }
      return out;
    } catch {
      return {};
    }
  }

  setExecutionSetting(name: ExecutionSettingName, value: string | undefined): void {
    const next: Partial<Record<ExecutionSettingName, string>> = { ...this.executionSettings() };
    if (value) next[name] = value;
    else delete next[name];
    this.app.saveLocalStorage(SETTINGS_STORAGE_KEY, Object.keys(next).length > 0 ? JSON.stringify(next) : null);
  }

  private connect(endpoint: string): void {
    this.connection?.stop();
    this.unsubscribe?.();
    this.connection = new CompanionConnection({ endpoint, probe: requestUrlProbe });
    this.unsubscribe = this.connection.onChange((s) => {
      for (const l of this.stateListeners) l(s);
    });
    this.connection.start();
  }

  private async activatePanel(): Promise<void> {
    const { workspace } = this.app;
    let leaf = workspace.getLeavesOfType(VIEW_TYPE)[0] ?? null;
    if (!leaf) {
      leaf = workspace.getRightLeaf(false);
      await leaf?.setViewState({ type: VIEW_TYPE, active: true });
    }
    if (leaf) await workspace.revealLeaf(leaf);
  }
}

class MonoclePanelView extends ItemView {
  private unsubscribe: (() => void) | undefined;
  private cancelActive: (() => void) | undefined;

  constructor(
    leaf: WorkspaceLeaf,
    private readonly plugin: MonoclePlugin,
  ) {
    super(leaf);
  }

  getViewType(): string {
    return VIEW_TYPE;
  }

  getDisplayText(): string {
    return "Monocle";
  }

  override getIcon(): string {
    return "glasses";
  }

  override async onOpen(): Promise<void> {
    const root = this.contentEl;
    root.empty();
    root.addClass("monocle-panel");
    const header = root.createDiv({ cls: "monocle-status" });
    const dot = header.createSpan({ cls: "monocle-status-dot" });
    const label = header.createSpan({ cls: "monocle-status-label" });
    const retry = header.createEl("button", { text: "Reconnect" });
    retry.addEventListener("click", () => void this.plugin.connection.check());
    const detail = root.createDiv({ cls: "monocle-status-detail" });
    const error = root.createDiv({ cls: "monocle-status-error" });

    const chat = root.createDiv({ cls: "monocle-chat" });
    const prompt = chat.createEl("textarea", {
      cls: "monocle-prompt",
      attr: { placeholder: "Ask Cravat… (Ctrl/Cmd+Enter to send)", rows: "3" },
    });
    const actions = chat.createDiv({ cls: "monocle-actions" });
    const send = actions.createEl("button", { cls: "mod-cta monocle-send", text: "Send" });
    const cancel = actions.createEl("button", { cls: "monocle-cancel", text: "Cancel" });
    const settingsRow = chat.createDiv({ cls: "monocle-settings" });
    const contextEl = chat.createEl("details", { cls: "monocle-context" });
    const contextSummary = contextEl.createEl("summary", { text: "Context" });
    const checkbox = (cls: string, text: string) => {
      const row = contextEl.createEl("label", { cls: "monocle-context-option" });
      const input = row.createEl("input", { cls, attr: { type: "checkbox", checked: "" } });
      row.appendText(` ${text}`);
      return input;
    };
    const useNote = checkbox("monocle-context-note", "Active note");
    const useSelection = checkbox("monocle-context-selection", "Selection");
    const pathList = (cls: string, placeholder: string) =>
      contextEl.createEl("textarea", { cls, attr: { rows: "2", placeholder } });
    const includeEl = pathList("monocle-context-include", "Also include notes (vault paths, one per line)");
    const excludeEl = pathList("monocle-context-exclude", "Exclude notes or folders (one per line; never sent or readable)");
    const describeContext = () => {
      const note = this.plugin.activeNoteSnapshot();
      contextSummary.setText(note ? `Context · ${note.path}` : "Context · no active note");
    };
    describeContext();
    this.registerEvent(this.app.workspace.on("active-leaf-change", describeContext));
    contextEl.addEventListener("toggle", describeContext);

    const meta = chat.createDiv({ cls: "monocle-execution" });
    const execError = chat.createDiv({ cls: "monocle-execution-error" });
    const output = chat.createDiv({ cls: "monocle-output" });
    cancel.disabled = true;
    execError.hide();

    let connected = false;
    let active: ExecutionHandle | undefined;
    let capabilitiesFor: string | undefined;
    const loadSettings = async (instanceId: string) => {
      if (capabilitiesFor === instanceId) return;
      capabilitiesFor = instanceId;
      const caps = await new ExecutionClient({ endpoint: this.plugin.connection.endpoint, fetch: rendererFetch }).capabilities();
      if (capabilitiesFor === instanceId) renderSettings(settingsRow, caps, this.plugin);
    };
    const sync = () => {
      send.disabled = !connected || active !== undefined;
      cancel.disabled = active === undefined;
    };
    const submit = async () => {
      const text = prompt.value.trim();
      if (!text || active || !connected) return;
      const context = buildExecutionContext({
        activeNote: this.plugin.activeNoteSnapshot(),
        includeActiveNote: useNote.checked,
        includeSelection: useSelection.checked,
        include: includeEl.value,
        exclude: excludeEl.value,
      });
      const handle = new ExecutionClient({ endpoint: this.plugin.connection.endpoint, fetch: rendererFetch }).execute(
        text,
        this.plugin.executionSettings(),
        context,
      );
      active = handle;
      sync();
      output.empty();
      output.dataset.state = "running";
      execError.hide();
      meta.setText("Starting…");
      let streamed = "";
      for await (const event of handle.events) {
        meta.dataset.executionId = event.executionId;
        if (event.type === "started") {
          const applied = Object.entries(event.settings ?? {}).map(([k, v]) => `${k}=${v}`);
          meta.setText(`Execution ${event.executionId} · ${[event.provider, ...applied].join(" · ")} · running`);
        } else if (event.type === "delta") output.setText((streamed += event.text));
        else {
          meta.setText(`Execution ${event.executionId || "(not started)"} · ${event.type}`);
          output.dataset.state = event.type;
          if (event.type === "completed") {
            output.empty();
            await MarkdownRenderer.render(this.app, event.text, output, "", this);
          } else if (event.type === "failed") {
            execError.setText(`${event.error.code}: ${event.error.message}`);
            execError.show();
          }
        }
      }
      active = undefined;
      sync();
    };
    send.addEventListener("click", () => void submit());
    cancel.addEventListener("click", () => void active?.cancel());
    this.cancelActive = () => void active?.cancel();
    prompt.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        void submit();
      }
    });

    this.unsubscribe = this.plugin.onState((s) => {
      connected = s.kind === "connected";
      if (s.kind === "connected") void loadSettings(s.health.instanceId);
      sync();
      dot.dataset.state = s.kind;
      label.setText(LABELS[s.kind]);
      detail.setText(
        s.kind === "connected" || s.kind === "incompatible"
          ? `${s.endpoint} · contract ${s.health.contractVersion} · started ${s.health.startedAt}`
          : s.endpoint,
      );
      error.setText(s.kind === "disconnected" || s.kind === "incompatible" ? s.error : "");
      error.toggle(s.kind === "disconnected" || s.kind === "incompatible");
    });
  }

  override async onClose(): Promise<void> {
    this.cancelActive?.();
    this.unsubscribe?.();
  }
}

class MonocleSettingTab extends PluginSettingTab {
  constructor(
    app: App,
    private readonly plugin: MonoclePlugin,
  ) {
    super(app, plugin);
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();
    const message = containerEl.createDiv({ cls: "setting-item-description" });
    new Setting(containerEl)
      .setName("Companion endpoint")
      .setDesc("Loopback URL of the local Monocle companion on this machine. Stored locally; not synced with the vault.")
      .addText((text) =>
        text
          .setPlaceholder(DEFAULT_COMPANION_ENDPOINT)
          .setValue(this.plugin.connection.endpoint === DEFAULT_COMPANION_ENDPOINT ? "" : this.plugin.connection.endpoint)
          .onChange((value) => {
            const parsed = parseCompanionEndpoint(value);
            message.setText(parsed.ok ? "" : parsed.error);
            if (parsed.ok && parsed.endpoint !== this.plugin.connection.endpoint) this.plugin.setEndpoint(parsed.endpoint);
          }),
      );
  }
}
