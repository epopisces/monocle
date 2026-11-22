import { describe, expect, it } from "vitest";
import { parseExecutionRequest } from "@monocle/contracts";

describe("execution request context", () => {
  it("accepts an active note, selection, inclusions and exclusions", () => {
    const body = {
      prompt: "summarise",
      context: {
        activeNote: { path: "people/Ada Example.md", content: "# Ada", selection: "Ada" },
        include: ["projects/Project Lantern.md"],
        exclude: ["work"],
      },
    };
    expect(parseExecutionRequest(body)).toEqual({ ok: true, request: body });
  });

  it("still accepts a prompt without context", () => {
    expect(parseExecutionRequest({ prompt: "hi" })).toEqual({ ok: true, request: { prompt: "hi" } });
  });

  it.each([
    [{ context: "x" }, /context must be an object/],
    [{ context: { pinned: [] } }, /unsupported context fields: pinned/],
    [{ context: { activeNote: { content: "x" } } }, /activeNote.path/],
    [{ context: { activeNote: { path: "a.md", content: 3 } } }, /activeNote.content/],
    [{ context: { activeNote: { path: "a.md", cursor: 1 } } }, /unsupported activeNote fields: cursor/],
    [{ context: { include: "a.md" } }, /include must be an array of non-empty strings/],
    [{ context: { exclude: [""] } }, /exclude must be an array of non-empty strings/],
    [{ context: { activeNote: { path: "a.md", content: "x".repeat(200_001) } } }, /context exceeds/],
  ])("rejects malformed context %j", (extra, message) => {
    const result = parseExecutionRequest({ prompt: "hi", ...extra });
    expect(result).toEqual({ ok: false, error: expect.stringMatching(message) });
  });
});
