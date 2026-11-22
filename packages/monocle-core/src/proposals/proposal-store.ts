import { createHash, randomUUID } from "node:crypto";
import { mkdir, readdir, readFile, rename, writeFile } from "node:fs/promises";
import { join } from "node:path";
import {
  CHANGE_SET_FORMAT,
  CHANGE_SET_FORMAT_VERSION,
  isPortableNotePath,
  type ChangeBase,
  type ChangeOperation,
  type ChangePatch,
  type ChangeProposal,
  type ChangeRisk,
  type ChangeSet,
  type ChangeSetSummary,
  type ChangeStatus,
  type ContentHash,
  type PortableChangeSet,
} from "@monocle/contracts";
import type { NotePlan } from "../operations/create-note.js";

export interface ProposalStoreOptions {
  /**
   * Machine-local data directory (never inside a vault); change sets go to `<dir>/proposals/<changeSetId>.json`.
   * Omitted: proposals live in memory only.
   */
  readonly dir?: string;
  readonly now?: () => Date;
}

export interface NewChangeProposal {
  readonly executionId: string;
  readonly conversationId?: string;
  readonly operation: ChangeOperation;
  readonly path: string;
  readonly noteId?: string;
  /** Base note content the change was made against; `null` when the note must not exist (`create`). */
  readonly base: { readonly content: string | null };
  readonly patch: ChangePatch;
  readonly risk: ChangeRisk;
  readonly summary?: string;
  readonly predecessorId?: string;
}

export interface ChangeSetFilter {
  readonly executionId?: string;
  readonly conversationId?: string;
}

export class InvalidProposalError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvalidProposalError";
  }
}

export class ChangeSetFormatError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ChangeSetFormatError";
  }
}

const OPERATIONS: readonly ChangeOperation[] = ["create", "modify", "delete"];
const RISKS: readonly ChangeRisk[] = ["low", "high"];
const STATUSES: readonly ChangeStatus[] = ["pending", "applied", "rejected", "conflicted", "failed", "superseded"];

export function contentHash(content: string): ContentHash {
  return `sha256:${createHash("sha256").update(content, "utf8").digest("hex")}`;
}

/**
 * A `create` proposal for a {@link NotePlan} from `planNote`. Defaults to `low` risk: it only ever adds a new file
 * (D06). Whoever applies it must still create exclusively and re-check that the planned ID is unused.
 */
export function noteCreationProposal(
  plan: NotePlan,
  session: { readonly executionId: string; readonly conversationId?: string; readonly risk?: ChangeRisk },
): NewChangeProposal {
  return {
    executionId: session.executionId,
    ...(session.conversationId !== undefined && { conversationId: session.conversationId }),
    operation: "create",
    path: plan.path,
    noteId: plan.id,
    base: { content: null },
    patch: { format: "replace", content: plan.content },
    risk: session.risk ?? "low",
  };
}

/** Portable JSON form of a change set ({@link PortableChangeSet}). */
export function serializeChangeSet(changeSet: ChangeSet): string {
  const body: PortableChangeSet = { format: CHANGE_SET_FORMAT, version: CHANGE_SET_FORMAT_VERSION, changeSet };
  return `${JSON.stringify(body, null, 2)}\n`;
}

/** Parses and fully validates {@link serializeChangeSet} output; throws {@link ChangeSetFormatError}. */
export function parseChangeSet(text: string): ChangeSet {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch (err) {
    throw new ChangeSetFormatError(`not JSON: ${(err as Error).message}`);
  }
  const v = value as Partial<PortableChangeSet> | null;
  if (typeof v !== "object" || v === null || v.format !== CHANGE_SET_FORMAT) {
    throw new ChangeSetFormatError(`not a ${CHANGE_SET_FORMAT} document`);
  }
  if (v.version !== CHANGE_SET_FORMAT_VERSION) throw new ChangeSetFormatError(`unsupported version ${String(v.version)}`);
  const set = v.changeSet as Partial<ChangeSet> | undefined;
  if (
    typeof set !== "object" ||
    set === null ||
    !isString(set.id) ||
    !isString(set.executionId) ||
    !isOptionalString(set.conversationId) ||
    !isString(set.createdAt) ||
    !isString(set.updatedAt) ||
    !Array.isArray(set.changes)
  ) {
    throw new ChangeSetFormatError("malformed change set");
  }
  set.changes.forEach((c: unknown, i) => {
    const problem = changeProblem(c, set as ChangeSet);
    if (problem) throw new ChangeSetFormatError(`change ${i}: ${problem}`);
  });
  return set as ChangeSet;
}

/**
 * Monocle-owned, machine-local record of change proposals grouped per Cravat execution (IMM-53). One change set
 * per execution; sets of other executions are never touched by operations on one. Proposals are not ingested into
 * the note index. Writes are atomic (temp file + rename) and serialized per change set.
 */
export class ProposalStore {
  private readonly sets = new Map<string, ChangeSet>();
  private readonly writes = new Map<string, Promise<void>>();
  private readonly dir: string | undefined;
  private readonly now: () => Date;
  private closed = false;

  private constructor(options: ProposalStoreOptions) {
    this.dir = options.dir === undefined ? undefined : join(options.dir, "proposals");
    this.now = options.now ?? (() => new Date());
  }

  /** Loads persisted change sets, skipping files that fail validation. */
  static async open(options: ProposalStoreOptions = {}): Promise<ProposalStore> {
    const store = new ProposalStore(options);
    if (!store.dir) return store;
    await mkdir(store.dir, { recursive: true, mode: 0o700 });
    for (const name of await readdir(store.dir)) {
      if (!name.endsWith(".json")) continue;
      let set: ChangeSet;
      try {
        set = parseChangeSet(await readFile(join(store.dir, name), "utf8"));
      } catch (err) {
        console.error(`Monocle: skipping change set ${name}: ${(err as Error).message}`);
        continue;
      }
      if (name !== `${set.id}.json` || store.changeSetForExecution(set.executionId)) continue;
      store.sets.set(set.id, set);
    }
    return store;
  }

  /** Most recently updated first. */
  list(filter: ChangeSetFilter = {}): ChangeSetSummary[] {
    return [...this.sets.values()]
      .filter((s) => filter.executionId === undefined || s.executionId === filter.executionId)
      .filter((s) => filter.conversationId === undefined || s.conversationId === filter.conversationId)
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      .map(({ changes, ...rest }) => {
        const counts = Object.fromEntries(STATUSES.map((s) => [s, 0])) as Record<ChangeStatus, number>;
        for (const c of changes) counts[c.status]++;
        return { ...rest, counts };
      });
  }

  get(changeSetId: string): ChangeSet | undefined {
    return this.sets.get(changeSetId);
  }

  changeSetForExecution(executionId: string): ChangeSet | undefined {
    for (const set of this.sets.values()) if (set.executionId === executionId) return set;
    return undefined;
  }

  getChange(changeId: string): ChangeProposal | undefined {
    for (const set of this.sets.values()) {
      const change = set.changes.find((c) => c.id === changeId);
      if (change) return change;
    }
    return undefined;
  }

  /** Records a pending proposal in its execution's change set, creating the set on first use. */
  propose(input: NewChangeProposal): ChangeProposal {
    const base = checkProposal(input);
    const at = this.now().toISOString();
    const existing = this.changeSetForExecution(input.executionId);
    if (existing && input.conversationId !== undefined && existing.conversationId !== input.conversationId) {
      throw new InvalidProposalError(`execution ${input.executionId} belongs to a different conversation`);
    }
    const set: ChangeSet = existing ?? {
      id: randomUUID(),
      executionId: input.executionId,
      ...(input.conversationId !== undefined && { conversationId: input.conversationId }),
      createdAt: at,
      updatedAt: at,
      changes: [],
    };
    const change: ChangeProposal = {
      id: randomUUID(),
      changeSetId: set.id,
      executionId: input.executionId,
      operation: input.operation,
      path: input.path,
      ...(input.noteId !== undefined && { noteId: input.noteId }),
      base,
      patch: input.patch,
      risk: input.risk,
      status: "pending",
      ...(input.summary !== undefined && { summary: input.summary }),
      ...(input.predecessorId !== undefined && { predecessorId: input.predecessorId }),
      createdAt: at,
      updatedAt: at,
    };
    this.save({ ...set, updatedAt: at, changes: [...set.changes, change] });
    return change;
  }

  /** Records the decision on a `pending` proposal. Decided proposals are immutable. */
  setStatus(changeId: string, status: Exclude<ChangeStatus, "pending">): ChangeProposal {
    const change = this.getChange(changeId);
    if (!change) throw new InvalidProposalError(`unknown change ${changeId}`);
    if (change.status !== "pending") throw new InvalidProposalError(`change ${changeId} is already ${change.status}`);
    if (!STATUSES.includes(status) || status === ("pending" as ChangeStatus)) {
      throw new InvalidProposalError(`invalid status ${String(status)}`);
    }
    const at = this.now().toISOString();
    const updated: ChangeProposal = { ...change, status, updatedAt: at };
    const set = this.sets.get(change.changeSetId)!;
    this.save({ ...set, updatedAt: at, changes: set.changes.map((c) => (c.id === changeId ? updated : c)) });
    return updated;
  }

  /** Resolves once every write issued so far has reached disk. */
  async flush(): Promise<void> {
    await Promise.all(this.writes.values());
  }

  async close(): Promise<void> {
    await this.flush();
    this.closed = true;
  }

  private save(set: ChangeSet): void {
    this.sets.set(set.id, set);
    const dir = this.dir;
    if (!dir || this.closed) return;
    const file = join(dir, `${set.id}.json`);
    const previous = this.writes.get(set.id) ?? Promise.resolve();
    const write = previous.then(async () => {
      const temp = `${file}.${process.pid}.tmp`;
      await writeFile(temp, serializeChangeSet(set), { encoding: "utf8", mode: 0o600 });
      await renameWithRetry(temp, file);
    });
    this.writes.set(
      set.id,
      write.catch((err: unknown) => {
        console.error(`Monocle: could not persist change set ${set.id}: ${(err as Error).message}`);
      }),
    );
  }
}

function checkProposal(input: NewChangeProposal): ChangeBase {
  if (!isString(input.executionId)) throw new InvalidProposalError("executionId is required");
  if (!OPERATIONS.includes(input.operation)) throw new InvalidProposalError(`unknown operation ${String(input.operation)}`);
  if (!RISKS.includes(input.risk)) throw new InvalidProposalError(`unknown risk ${String(input.risk)}`);
  if (!isPortableNotePath(input.path)) throw new InvalidProposalError(`"${input.path}" is not a vault-relative note path`);
  const content = input.base.content;
  const shape = operationProblem(input.operation, content === null, input.patch);
  if (shape) throw new InvalidProposalError(shape);
  return content === null ? { hash: null } : { hash: contentHash(content), content };
}

/** `create` needs an absent base and full content; `modify` a base and content; `delete` a base and no content. */
function operationProblem(operation: ChangeOperation, baseAbsent: boolean, patch: ChangePatch | undefined): string | undefined {
  const isReplace = patch?.format === "replace" && typeof patch.content === "string";
  const isDelete = patch?.format === "delete";
  if (!isReplace && !isDelete) return "patch must be {format:\"replace\", content} or {format:\"delete\"}";
  if (operation === "create" && (!baseAbsent || !isReplace)) return "create needs base content null and a replace patch";
  if (operation === "modify" && (baseAbsent || !isReplace)) return "modify needs base content and a replace patch";
  if (operation === "delete" && (baseAbsent || !isDelete)) return "delete needs base content and a delete patch";
  return undefined;
}

function changeProblem(value: unknown, set: ChangeSet): string | undefined {
  if (typeof value !== "object" || value === null) return "not an object";
  const c = value as Partial<ChangeProposal>;
  if (!isString(c.id) || !isString(c.createdAt) || !isString(c.updatedAt)) return "missing id or timestamps";
  if (c.changeSetId !== set.id || c.executionId !== set.executionId) return "does not belong to this change set";
  if (!OPERATIONS.includes(c.operation!)) return "unknown operation";
  if (!RISKS.includes(c.risk!)) return "unknown risk";
  if (!STATUSES.includes(c.status!)) return "unknown status";
  if (!isString(c.path) || !isPortableNotePath(c.path)) return "invalid path";
  if (!isOptionalString(c.noteId) || !isOptionalString(c.summary) || !isOptionalString(c.predecessorId)) {
    return "invalid noteId, summary or predecessorId";
  }
  const base = c.base as { hash?: unknown; content?: unknown } | undefined;
  if (typeof base !== "object" || base === null) return "missing base";
  if (base.hash !== null) {
    if (typeof base.content !== "string") return "base content missing";
    if (base.hash !== contentHash(base.content)) return "base hash does not match base content";
  }
  return operationProblem(c.operation!, base.hash === null, c.patch);
}

const isString = (v: unknown): v is string => typeof v === "string" && v.length > 0;
const isOptionalString = (v: unknown): boolean => v === undefined || isString(v);

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
