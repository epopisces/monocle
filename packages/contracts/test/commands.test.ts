import { describe, expect, it } from "vitest";
import { findCommand, missingContext, parseChatInput } from "@monocle/contracts";

describe("chat input routing", () => {
  it("treats ordinary text as a free-form request for Cravat", () => {
    expect(parseChatInput("  summarise my week ")).toEqual({ kind: "freeform", prompt: "summarise my week" });
  });

  it("routes a registered deterministic command to Monocle with its argument", () => {
    const parsed = parseChatInput("/search  lanternfish 7731 ");
    expect(parsed).toMatchObject({ kind: "command", argument: "lanternfish 7731" });
    expect(parsed.kind === "command" && parsed.command).toMatchObject({ id: "search", route: "monocle" });
  });

  it("routes /lookup to Cravat and /validate to Monocle", () => {
    const lookup = parseChatInput("/lookup who owns Project Lantern?");
    const validate = parseChatInput("/validate");
    expect(lookup.kind === "command" && lookup.command.route).toBe("cravat");
    expect(validate).toMatchObject({ kind: "command", argument: "" });
    expect(validate.kind === "command" && validate.command.route).toBe("monocle");
  });

  it("rejects an unknown command instead of sending it to the agent, listing the known ones", () => {
    const parsed = parseChatInput("/valdiate");
    expect(parsed.kind).toBe("unknown");
    expect(parsed.kind === "unknown" && parsed.message).toMatch(/\/valdiate.*\/validate.*\/lookup/);
  });

  it("keeps text that merely starts with a path as free-form", () => {
    expect(parseChatInput("/etc/hosts — what is this file?").kind).toBe("freeform");
  });
});

describe("command context requirements", () => {
  const validate = findCommand("validate")!;
  const lookup = findCommand("lookup")!;
  const search = findCommand("search")!;

  it("names the missing active note", () => {
    expect(missingContext(validate, { argument: "", activeNote: undefined, vault: true })).toEqual([
      expect.stringMatching(/\/validate needs an active note/),
    ]);
  });

  it("names a missing vault and a missing argument", () => {
    const missing = missingContext(search, { argument: "  ", vault: false });
    expect(missing).toEqual([expect.stringMatching(/needs a query/), expect.stringMatching(/vault/)]);
  });

  it("accepts the selection as the argument of a command that allows it", () => {
    expect(missingContext(lookup, { argument: "", activeNote: { path: "a.md", selection: "Lantern" }, vault: true })).toEqual([]);
    expect(missingContext(lookup, { argument: "", activeNote: { path: "a.md" }, vault: true })).toEqual([
      expect.stringMatching(/\/lookup needs a question.*select text/),
    ]);
  });

  it("is satisfied when everything required is present", () => {
    expect(missingContext(validate, { argument: "", activeNote: { path: "a.md" }, vault: true })).toEqual([]);
  });
});
