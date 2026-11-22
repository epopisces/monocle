import { describe, expect, it } from "vitest";
import { defaultDataDir } from "../src/data-dir.js";

describe("defaultDataDir", () => {
  it("uses the machine-local (non-roaming) app data folder on Windows", () => {
    expect(defaultDataDir("win32", { LOCALAPPDATA: "C:\\Users\\u\\AppData\\Local" }, "C:\\Users\\u")).toBe(
      "C:\\Users\\u\\AppData\\Local\\Monocle",
    );
  });

  it("uses Application Support on macOS", () => {
    expect(defaultDataDir("darwin", {}, "/Users/u")).toBe("/Users/u/Library/Application Support/Monocle");
  });

  it("uses the XDG state directory on Linux, falling back to ~/.local/state", () => {
    expect(defaultDataDir("linux", { XDG_STATE_HOME: "/x/state" }, "/home/u")).toBe("/x/state/monocle");
    expect(defaultDataDir("linux", {}, "/home/u")).toBe("/home/u/.local/state/monocle");
  });
});
