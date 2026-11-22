import {
  ItemView,
  MarkdownRenderer,
  MarkdownView,
  Notice,
  Plugin,
  PluginSettingTab,
  Setting,
  requestUrl,
  type App,
  type WorkspaceLeaf,
} from "obsidian";
import {
  COMMANDS,
  DEFAULT_COMPANION_ENDPOINT,
  EXECUTION_SETTING_NAMES,
  parseChatInput,
  type CommandDefinition,
  type Conversation,
  type ConversationExecution,
  type ExecutionCapabilities,
  type ExecutionSettingName,
  type ExecutionSettings,
  type ProviderSessionInfo,
} from "@monocle/contracts";
import { CompanionConnection, type ConnectionState, type HealthProbe } from "./connection.js";
import { buildExecutionContext, type ActiveNoteSnapshot } from "./context.js";
import { parseCompanionEndpoint } from "./endpoint.js";
import { ConversationClient } from "./conversation-client.js";
import { IndexHealthMonitor } from "./index-health.js";
import { installIndexHealthUi, requestUrlCompanion } from "./index-ui.js";
import { ExecutionClient, type ExecutionHandle, type FetchLike } from "./execution-client.js";
import { CommandRunner } from "./command-runner.js";

/** Runs a registry command in the open panel; `note` is the note the command targets, if any. */
type PanelCommand = (command: CommandDefinition, argument: string, note: ActiveNoteSnapshot | undefined) => Promise<void>;

/**
 * Executions stream over the renderer's `fetch` (`requestUrl` buffers whole responses). The companion
 * allows Obsidian's `app://obsidian.md` origin via CORS and rejects every other browser origin.
 */
const rendererFetch: FetchLike = (input, init) => window.fetch(input, init);

const VIEW_TYPE = "monocle-panel";
/** Host-local (per vault, per machine) key; the endpoint must not sync through the vault (D01). */
const ENDPOINT_STORAGE_KEY = "monocle:companion-endpoint";
/**
 * Host-local key for the open conversation. Only the ID is kept here; the conversation itself lives in the
 * companion's machine-local data directory and never in the vault or plugin data (D05).
 */
const CONVERSATION_STORAGE_KEY = "monocle:conversation-id";
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

/** How an execution relates to the provider context of earlier messages; `undefined` when there is nothing to say. */
function describeSession(session: ProviderSessionInfo | undefined): string | undefined {
  if (!session) return undefined;
  if (session.continuity === "resumed") return "Continued provider session";
  if (session.continuity === "new") return "New provider session";
  return `Earlier context unavailable to the provider${session.reason ? `: ${session.reason}` : ""}`;
}

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
    this.registerRegistryCommands();
    this.addSettingTab(new MonocleSettingTab(this.app, this));
  }

  /**
   * Surfaces every registry command (IMM-51) in the palette and context menus. All entry points run through
   * {@link runCommand}, so missing context is reported the same way everywhere.
   */
  private registerRegistryCommands(): void {
    for (const command of COMMANDS.filter((c) => c.surfaces.includes("palette"))) {
      // Plain callback (not checkCallback) so a missing note is explained instead of the command vanishing.
      this.addCommand({ id: command.id, name: command.name, callback: () => void this.runCommand(command) });
    }
    const menuTitle = (c: CommandDefinition) => `Monocle: ${c.name}`;
    this.registerEvent(
      this.app.workspace.on("editor-menu", (menu, editor, info) => {
        const file = info.file;
        if (!file) return;
        const selection = editor.getSelection();
        const note = { path: file.path, content: editor.getValue(), ...(selection && { selection }) };
        for (const command of COMMANDS.filter((c) => c.surfaces.includes("editor-menu"))) {
          menu.addItem((item) =>
            item
              .setTitle(menuTitle(command))
              .setIcon("glasses")
              .onClick(() => void this.runCommand(command, "", note)),
          );
        }
      }),
    );
    this.registerEvent(
      this.app.workspace.on("file-menu", (menu, file) => {
        if (!("extension" in file) || file.extension !== "md") return;
        for (const command of COMMANDS.filter((c) => c.surfaces.includes("file-menu"))) {
          menu.addItem((item) =>
            item
              .setTitle(menuTitle(command))
              .setIcon("glasses")
              .onClick(() => void this.runCommand(command, "", { path: file.path, content: "" })),
          );
        }
      }),
    );
  }

  /** Set by the open panel; commands render their result or error there. */
  panelCommand: PanelCommand | undefined;

  /**
   * Runs a registry command from any surface. `note` defaults to the last focused Markdown note; pass `null`
   * for "no note".
   */
  async runCommand(command: CommandDefinition, argument = "", note?: ActiveNoteSnapshot | null): Promise<void> {
    const target = note === undefined ? this.activeNoteSnapshot() : (note ?? undefined);
    await this.activatePanel();
    if (!this.panelCommand) {
      new Notice("Monocle: open the Monocle panel to run commands");
      return;
    }
    await this.panelCommand(command, argument, target);
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

  storedConversationId(): string | undefined {
    const saved: unknown = this.app.loadLocalStorage(CONVERSATION_STORAGE_KEY);
    return typeof saved === "string" && saved ? saved : undefined;
  }

  setConversationId(id: string | undefined): void {
    this.app.saveLocalStorage(CONVERSATION_STORAGE_KEY, id ?? null);
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

    const bar = root.createDiv({ cls: "monocle-conversations" });
    const picker = bar.createEl("select", { cls: "dropdown monocle-conversation-select" });
    const newConversation = bar.createEl("button", { cls: "monocle-new-conversation", text: "New conversation" });
    const transcript = root.createDiv({ cls: "monocle-transcript" });

    const chat = root.createDiv({ cls: "monocle-chat" });
    const prompt = chat.createEl("textarea", {
      cls: "monocle-prompt",
      attr: { placeholder: "Ask Cravat, or /validate, /backlinks, /search <query>, /lookup <question>… (Ctrl/Cmd+Enter to send)", rows: "3" },
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
    const execSession = chat.createDiv({ cls: "monocle-execution-session" });
    const execError = chat.createDiv({ cls: "monocle-execution-error" });
    const output = chat.createDiv({ cls: "monocle-output" });
    cancel.disabled = true;
    execError.hide();

    let connected = false;
    let active: ExecutionHandle | undefined;
    let conversationId = this.plugin.storedConversationId();
    /** Execution shown in the live area below; the transcript lists the conversation's other executions. */
    let liveExecutionId: string | undefined;
    let refreshToken = 0;
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
      picker.disabled = active !== undefined;
      newConversation.disabled = active !== undefined;
    };
    const conversationsClient = () =>
      new ConversationClient({ endpoint: this.plugin.connection.endpoint, fetch: rendererFetch });
    const adopt = (id: string | undefined) => {
      conversationId = id;
      this.plugin.setConversationId(id);
    };
    const clearLive = () => {
      liveExecutionId = undefined;
      output.empty();
      delete output.dataset.state;
      meta.setText("");
      execSession.setText("");
      execError.hide();
    };
    const renderTurn = async (execution: ConversationExecution) => {
      const turn = transcript.createDiv({ cls: "monocle-turn", attr: { "data-status": execution.status } });
      turn.createDiv({ cls: "monocle-turn-prompt", text: execution.prompt });
      const response = turn.createDiv({ cls: "monocle-turn-response" });
      if (execution.status === "completed" && execution.response !== undefined) {
        await MarkdownRenderer.render(this.app, execution.response, response, "", this);
      } else if (execution.response) response.setText(execution.response);
      const details = [execution.status, execution.provider, describeSession(execution.providerSession)];
      if (execution.status === "interrupted") details.push("the companion stopped before it finished");
      turn.createDiv({ cls: "monocle-turn-meta", text: details.filter(Boolean).join(" · ") });
      if (execution.error) turn.createDiv({ cls: "monocle-turn-error", text: `${execution.error.code}: ${execution.error.message}` });
    };
    /** Reloads the conversation list and the open conversation's transcript from the companion. */
    const refresh = async () => {
      if (!connected) return;
      const token = ++refreshToken;
      const client = conversationsClient();
      let summaries;
      let conversation: Conversation | undefined;
      try {
        summaries = await client.list();
        conversation = summaries && conversationId !== undefined ? await client.get(conversationId) : undefined;
      } catch {
        return;
      }
      if (token !== refreshToken) return;
      bar.toggle(summaries !== undefined);
      if (summaries && conversationId !== undefined && !conversation && !active) adopt(undefined);
      picker.empty();
      picker.createEl("option", { text: "New conversation", value: "" });
      for (const c of summaries ?? []) picker.createEl("option", { text: c.title, value: c.id });
      picker.value = conversationId ?? "";
      transcript.empty();
      for (const execution of conversation?.executions ?? []) {
        if (execution.executionId !== liveExecutionId) await renderTurn(execution);
      }
    };
    picker.addEventListener("change", () => {
      if (active) return;
      adopt(picker.value || undefined);
      clearLive();
      void refresh();
    });
    newConversation.addEventListener("click", () => {
      if (active) return;
      adopt(undefined);
      clearLive();
      void refresh();
    });
    const contextFor = (note: ActiveNoteSnapshot | undefined) =>
      buildExecutionContext({
        activeNote: note,
        includeActiveNote: useNote.checked,
        includeSelection: useSelection.checked,
        include: includeEl.value,
        exclude: excludeEl.value,
      });
    const beginLive = (title: string) => {
      // The previous live execution now belongs in the transcript.
      liveExecutionId = undefined;
      void refresh();
      output.empty();
      output.dataset.state = "running";
      delete meta.dataset.executionId;
      execError.hide();
      execSession.setText("");
      meta.setText(title);
    };
    const showFailure = (title: string, code: string, message: string) => {
      output.empty();
      output.dataset.state = "failed";
      meta.setText(title);
      execError.setText(`${code}: ${message}`);
      execError.show();
    };
    const stream = async (handle: ExecutionHandle) => {
      active = handle;
      sync();
      let streamed = "";
      for await (const event of handle.events) {
        meta.dataset.executionId = event.executionId;
        if (event.type === "started") {
          liveExecutionId = event.executionId;
          if (event.conversationId !== undefined && event.conversationId !== conversationId) adopt(event.conversationId);
          const applied = Object.entries(event.settings ?? {}).map(([k, v]) => `${k}=${v}`);
          meta.setText(`Execution ${event.executionId} · ${[event.provider, ...applied].join(" · ")} · running`);
        } else if (event.type === "delta") output.setText((streamed += event.text));
        else {
          meta.setText(`Execution ${event.executionId || "(not started)"} · ${event.type}`);
          output.dataset.state = event.type;
          execSession.setText(describeSession(event.providerSession) ?? "");
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
      void refresh();
    };
    let commandRunning = false;
    /** Registry commands (IMM-51): deterministic ones render here without Cravat; agentic ones stream. */
    const runCommand: PanelCommand = async (command, argument, note) => {
      if (active || commandRunning) {
        new Notice("Monocle: wait for the running request to finish");
        return;
      }
      const title = `Monocle /${command.id}`;
      commandRunning = true;
      beginLive(`${title} · running`);
      try {
        const runner = new CommandRunner({
          endpoint: this.plugin.connection.endpoint,
          fetch: rendererFetch,
          executions: new ExecutionClient({ endpoint: this.plugin.connection.endpoint, fetch: rendererFetch }),
        });
        const outcome = await runner.run({
          command,
          argument,
          activeNote: note,
          context: contextFor(note),
          settings: this.plugin.executionSettings(),
          ...(conversationId !== undefined && { conversationId }),
        });
        if (outcome.kind === "execution") await stream(outcome.handle);
        else if (outcome.kind === "error") showFailure(`${title} · failed`, outcome.error.code, outcome.error.message);
        else {
          meta.setText(`${title} · completed`);
          output.dataset.state = "completed";
          output.empty();
          await MarkdownRenderer.render(this.app, outcome.result.markdown, output, note?.path ?? "", this);
        }
      } finally {
        commandRunning = false;
      }
    };
    this.plugin.panelCommand = runCommand;
    this.register(() => {
      if (this.plugin.panelCommand === runCommand) this.plugin.panelCommand = undefined;
    });
    const submit = async () => {
      const text = prompt.value.trim();
      if (!text || active || commandRunning || !connected) return;
      const parsed = parseChatInput(text);
      if (parsed.kind === "unknown") {
        beginLive("");
        return showFailure("Monocle · failed", "unknown_command", parsed.message);
      }
      if (parsed.kind === "command") return runCommand(parsed.command, parsed.argument, this.plugin.activeNoteSnapshot());
      const handle = new ExecutionClient({ endpoint: this.plugin.connection.endpoint, fetch: rendererFetch }).execute(
        parsed.prompt,
        this.plugin.executionSettings(),
        { ...(conversationId !== undefined && { conversationId }), context: contextFor(this.plugin.activeNoteSnapshot()) },
      );
      beginLive("Starting…");
      await stream(handle);
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
      const wasConnected = connected;
      connected = s.kind === "connected";
      if (s.kind === "connected") void loadSettings(s.health.instanceId);
      sync();
      if (connected && !wasConnected) void refresh();
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
