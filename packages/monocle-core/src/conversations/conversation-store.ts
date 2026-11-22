import { randomUUID } from "node:crypto";
import { mkdir, readdir, readFile, rename, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type {
  Conversation,
  ConversationExecution,
  ConversationSummary,
  ExecutionError,
  ProviderSessionInfo,
} from "@monocle/contracts";
import { isConversationId } from "@monocle/contracts";

/** On-disk envelope; bump `version` on incompatible changes to the stored shape. */
const FORMAT = "monocle.conversation";
const FORMAT_VERSION = 1;
const TITLE_LENGTH = 60;

export interface ConversationStoreOptions {
  /**
   * Machine-local directory to persist conversations in (one JSON file per conversation). Must not be inside a
   * synchronized vault. Omitted: conversations live in memory only.
   */
  readonly dir?: string;
  /** Current companion instance; `running` executions recorded by any other instance become `interrupted`. */
  readonly instanceId: string;
  readonly now?: () => Date;
}

export type NewConversationExecution = Omit<ConversationExecution, "status" | "endedAt" | "response" | "error">;

export interface ConversationExecutionOutcome {
  readonly status: Exclude<ConversationExecution["status"], "running">;
  readonly response?: string;
  readonly error?: ExecutionError;
  readonly providerSession?: ProviderSessionInfo;
}

interface StoredFile {
  readonly format: typeof FORMAT;
  readonly version: number;
  readonly conversation: Conversation;
}

const INTERRUPTED: ExecutionError = {
  code: "connection_lost",
  message: "the companion stopped before this execution finished; its outcome is unknown",
};

export function conversationTitle(prompt: string): string {
  const line = prompt.trim().split(/\r?\n/, 1)[0]!.trim();
  return line.length > TITLE_LENGTH ? `${line.slice(0, TITLE_LENGTH - 1)}…` : line;
}

function isStoredFile(value: unknown): value is StoredFile {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Partial<StoredFile>;
  return (
    v.format === FORMAT &&
    v.version === FORMAT_VERSION &&
    typeof v.conversation?.id === "string" &&
    isConversationId(v.conversation.id) &&
    Array.isArray(v.conversation.executions)
  );
}

/**
 * Monocle-owned, machine-local record of conversations and the Cravat executions in them (IMM-50). Writes are
 * atomic (temp file + rename) and serialized per conversation.
 */
export class ConversationStore {
  private readonly conversations = new Map<string, Conversation>();
  private readonly writes = new Map<string, Promise<void>>();
  private readonly dir: string | undefined;
  private readonly now: () => Date;
  private closed = false;

  private constructor(options: ConversationStoreOptions) {
    this.dir = options.dir === undefined ? undefined : join(options.dir, "conversations");
    this.now = options.now ?? (() => new Date());
  }

  /** Loads persisted conversations, skipping unreadable files, and marks orphaned executions `interrupted`. */
  static async open(options: ConversationStoreOptions): Promise<ConversationStore> {
    const store = new ConversationStore(options);
    if (!store.dir) return store;
    await mkdir(store.dir, { recursive: true, mode: 0o700 });
    for (const name of await readdir(store.dir)) {
      if (!name.endsWith(".json")) continue;
      let parsed: unknown;
      try {
        parsed = JSON.parse(await readFile(join(store.dir, name), "utf8"));
      } catch {
        continue;
      }
      if (!isStoredFile(parsed) || name !== `${parsed.conversation.id}.json`) continue;
      let conversation = parsed.conversation;
      const orphaned = (e: ConversationExecution) => e.status === "running" && e.instanceId !== options.instanceId;
      const hasOrphans = conversation.executions.some(orphaned);
      if (hasOrphans) {
        conversation = {
          ...conversation,
          executions: conversation.executions.map((e) => (orphaned(e) ? { ...e, status: "interrupted", error: INTERRUPTED } : e)),
        };
      }
      store.conversations.set(conversation.id, conversation);
      if (hasOrphans) store.persist(conversation);
    }
    await store.flush();
    return store;
  }

  /** Most recently updated first. */
  list(): ConversationSummary[] {
    return [...this.conversations.values()]
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      .map(({ id, title, createdAt, updatedAt, executions }) => ({
        id,
        title,
        createdAt,
        updatedAt,
        executionCount: executions.length,
      }));
  }

  get(id: string): Conversation | undefined {
    return this.conversations.get(id);
  }

  create(title: string): Conversation {
    const at = this.now().toISOString();
    const conversation: Conversation = { id: randomUUID(), title, createdAt: at, updatedAt: at, executions: [] };
    this.save(conversation);
    return conversation;
  }

  /** The conversation's execution that is still running, if any. */
  running(conversationId: string): ConversationExecution | undefined {
    return this.conversations.get(conversationId)?.executions.find((e) => e.status === "running");
  }

  beginExecution(conversationId: string, execution: NewConversationExecution): void {
    this.update(conversationId, (executions) => [...executions, { ...execution, status: "running" }]);
  }

  finishExecution(conversationId: string, executionId: string, outcome: ConversationExecutionOutcome): void {
    const endedAt = this.now().toISOString();
    this.update(conversationId, (executions) =>
      executions.map((e) => (e.executionId === executionId ? { ...e, ...outcome, endedAt } : e)),
    );
  }

  /** Resolves once every write issued so far has reached disk. */
  async flush(): Promise<void> {
    await Promise.all(this.writes.values());
  }

  /**
   * Flushes and stops persisting. Executions still running stay recorded as `running` and are reported as
   * `interrupted` by the next instance, because their outcome was not observed.
   */
  async close(): Promise<void> {
    this.closed = true;
    await this.flush();
  }

  private update(id: string, change: (executions: readonly ConversationExecution[]) => ConversationExecution[]): void {
    const conversation = this.conversations.get(id);
    if (!conversation) throw new Error(`unknown conversation ${id}`);
    this.save({ ...conversation, executions: change(conversation.executions), updatedAt: this.now().toISOString() });
  }

  private save(conversation: Conversation): void {
    this.conversations.set(conversation.id, conversation);
    this.persist(conversation);
  }

  private persist(conversation: Conversation): void {
    const dir = this.dir;
    if (!dir || this.closed) return;
    const file = join(dir, `${conversation.id}.json`);
    const body: StoredFile = { format: FORMAT, version: FORMAT_VERSION, conversation };
    const previous = this.writes.get(conversation.id) ?? Promise.resolve();
    const write = previous.then(async () => {
      const temp = `${file}.${process.pid}.tmp`;
      await writeFile(temp, `${JSON.stringify(body, null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
      await renameWithRetry(temp, file);
    });
    // A failed write must not wedge later writes; the next save rewrites the whole conversation anyway.
    this.writes.set(
      conversation.id,
      write.catch((err: unknown) => {
        console.error(`Monocle: could not persist conversation ${conversation.id}: ${(err as Error).message}`);
      }),
    );
  }
}

/** Windows may briefly refuse to replace a file another process (antivirus, indexer) has open. */
async function renameWithRetry(from: string, to: string): Promise<void> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await rename(from, to);
    } catch (err) {
      const code = (err as NodeJS.ErrnoException).code;
      if (attempt >= 5 || (code !== "EPERM" && code !== "EACCES" && code !== "EBUSY")) throw err;
      await new Promise((r) => setTimeout(r, 20 * (attempt + 1)));
    }
  }
}
