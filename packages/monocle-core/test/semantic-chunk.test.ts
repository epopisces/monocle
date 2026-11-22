import { describe, expect, it } from "vitest";
import { chunkNote } from "@monocle/core";

describe("chunkNote", () => {
  it("splits on headings and keeps the heading trail with each passage", () => {
    const body = "Intro line.\n\n# Alpha\n\nAlpha text.\n\n## Beta\n\nBeta text.\n";
    const chunks = chunkNote("notes/A.md", body);
    expect(chunks.map((c) => [c.heading, c.text])).toEqual([
      ["", "Intro line."],
      ["Alpha", "# Alpha\n\nAlpha text."],
      ["Alpha > Beta", "## Beta\n\nBeta text."],
    ]);
    expect(chunks.map((c) => c.ordinal)).toEqual([0, 1, 2]);
  });

  it("derives passage IDs from path and content so unchanged passages keep their ID", () => {
    const before = chunkNote("n.md", "# A\n\none\n\n# B\n\ntwo\n");
    const after = chunkNote("n.md", "# New\n\ninserted\n\n# A\n\none\n\n# B\n\ntwo changed\n");
    const ids = (cs: typeof before) => new Map(cs.map((c) => [c.text, c.passageId]));
    expect(ids(after).get("# A\n\none")).toBe(ids(before).get("# A\n\none"));
    expect(ids(after).get("# B\n\ntwo changed")).not.toBe(ids(before).get("# B\n\ntwo"));
    expect(before[0]!.passageId.startsWith("n.md#")).toBe(true);
  });

  it("gives repeated identical passages distinct IDs", () => {
    const chunks = chunkNote("n.md", "# Same\n\nx\n\n# Same\n\nx\n");
    expect(new Set(chunks.map((c) => c.passageId)).size).toBe(2);
  });

  it("splits oversized sections on paragraph boundaries and drops empty sections", () => {
    const para = "word ".repeat(60).trim();
    const chunks = chunkNote("n.md", `# Big\n\n${para}\n\n${para}\n\n${para}\n\n# Empty\n\n`, { maxChars: 700 });
    expect(chunks.length).toBe(2);
    expect(chunks.every((c) => c.text.length <= 700 && c.heading === "Big")).toBe(true);
  });

  it("ignores headings inside fenced code", () => {
    const chunks = chunkNote("n.md", "# Real\n\n```\n# not a heading\n```\n");
    expect(chunks).toHaveLength(1);
  });
});
