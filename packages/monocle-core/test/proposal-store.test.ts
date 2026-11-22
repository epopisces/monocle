import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChangeSetFormatError, InvalidProposalError, ProposalStore, parseChangeSet, serializeChangeSet } from "@monocle/core";

let dir: string;
beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "monocle-proposals-"));
});
afterEach(() => rmSync(dir, { recursive: true, force: true }));

const createNote = {
  operation: "create",
  path: "inbox/New idea.md",
  noteId: "fx-0004",
  base: { content: null },
  patch: { format: "replace", content: "---\nid: fx-0004\n---\n# New idea\n" },
  risk: "low",
} as const;

const editNote = {
  operation: "modify",
  path: "notes/Alpha.md",
  noteId: "fx-0001",
  base: { content: "# Alpha\n" },
  patch: { format: "replace", content: "# Alpha\n\nMore.\n" },
  risk: "high",
} as const;

describe("ProposalStore", () => {
  it("links multiple changes from one execution in a single change set", async () => {
    const store = await ProposalStore.open({ dir });
    const a = store.propose({ executionId: "exec-1", conversationId: "conv-1", ...createNote });
    const b = store.propose({ executionId: "exec-1", conversationId: "conv-1", ...editNote });

    const set = store.changeSetForExecution("exec-1")!;
    expect(set.conversationId).toBe("conv-1");
    expect(set.changes.map((c) => c.id)).toEqual([a.id, b.id]);
    expect(set.changes.every((c) => c.changeSetId === set.id && c.status === "pending")).toBe(true);
    expect(b.base).toEqual({
      hash: "sha256:017b70af1737a855266fc9eb9b3f88917dc972f20d2a1c7d6baa03b85260e8b8",
      content: "# Alpha\n",
    });
    expect(a.base).toEqual({ hash: null });
  });

  it("preserves pending proposals and their decisions across a restart", async () => {
    const first = await ProposalStore.open({ dir });
    const a = first.propose({ executionId: "exec-1", ...createNote });
    const b = first.propose({ executionId: "exec-1", ...editNote });
    first.setStatus(b.id, "rejected");
    await first.close();

    const second = await ProposalStore.open({ dir });
    const set = second.changeSetForExecution("exec-1")!;
    expect(set.changes.map((c) => [c.id, c.status])).toEqual([
      [a.id, "pending"],
      [b.id, "rejected"],
    ]);
    expect(set.changes[1]!.patch).toEqual(editNote.patch);
  });

  it("keeps each execution's changes isolated from other sessions", async () => {
    const store = await ProposalStore.open({ dir });
    const mine = store.propose({ executionId: "exec-1", conversationId: "conv-1", ...createNote });
    const theirs = store.propose({ executionId: "exec-2", conversationId: "conv-1", ...editNote });
    store.propose({ executionId: "exec-3", conversationId: "conv-2", ...editNote });
    store.setStatus(theirs.id, "applied");

    expect(store.changeSetForExecution("exec-1")!.changes).toEqual([mine]);
    expect(store.list({ executionId: "exec-1" }).map((s) => [s.executionId, s.counts.pending])).toEqual([["exec-1", 1]]);
    expect(store.list({ conversationId: "conv-1" }).map((s) => s.executionId).sort()).toEqual(["exec-1", "exec-2"]);
    expect(store.changeSetForExecution("exec-unknown")).toBeUndefined();
  });

  it("only lets a pending proposal be decided once", async () => {
    const store = await ProposalStore.open();
    const change = store.propose({ executionId: "exec-1", ...editNote });
    store.setStatus(change.id, "applied");
    expect(() => store.setStatus(change.id, "rejected")).toThrow(InvalidProposalError);
  });

  it("rejects proposals whose base and patch do not fit the operation", async () => {
    const store = await ProposalStore.open();
    expect(() => store.propose({ executionId: "e", ...createNote, base: { content: "x" } })).toThrow(InvalidProposalError);
    expect(() => store.propose({ executionId: "e", ...editNote, patch: { format: "delete" } })).toThrow(InvalidProposalError);
    expect(() => store.propose({ executionId: "e", ...editNote, path: "../outside.md" })).toThrow(InvalidProposalError);
    expect(store.changeSetForExecution("e")).toBeUndefined();
  });
});

describe("portable change sets", () => {
  it("round-trips through serialization", async () => {
    const store = await ProposalStore.open();
    store.propose({ executionId: "exec-1", conversationId: "conv-1", summary: "add idea", ...createNote });
    store.propose({ executionId: "exec-1", conversationId: "conv-1", ...editNote });
    store.propose({
      executionId: "exec-1",
      operation: "delete",
      path: "notes/Old.md",
      base: { content: "# Old\n" },
      patch: { format: "delete" },
      risk: "high",
    });
    const set = store.changeSetForExecution("exec-1")!;

    const text = serializeChangeSet(set);
    expect(JSON.parse(text)).toMatchObject({ format: "monocle.change-set", version: 1 });
    expect(parseChangeSet(text)).toEqual(set);
  });

  it("rejects a document whose base content no longer matches its hash", async () => {
    const store = await ProposalStore.open();
    store.propose({ executionId: "exec-1", ...editNote });
    const doc = JSON.parse(serializeChangeSet(store.changeSetForExecution("exec-1")!));
    doc.changeSet.changes[0].base.content = "# Tampered\n";
    expect(() => parseChangeSet(JSON.stringify(doc))).toThrow(ChangeSetFormatError);
    expect(() => parseChangeSet(JSON.stringify({ ...doc, version: 2 }))).toThrow(/unsupported version/);
  });

  it("skips invalid files on load without losing valid change sets", async () => {
    const first = await ProposalStore.open({ dir });
    first.propose({ executionId: "exec-1", ...editNote });
    await first.close();
    writeFileSync(join(dir, "proposals", "garbage.json"), "{not json");
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});

    const second = await ProposalStore.open({ dir });
    expect(second.list().map((s) => s.executionId)).toEqual(["exec-1"]);
    expect(errors).toHaveBeenCalledOnce();
    errors.mockRestore();
  });
});
