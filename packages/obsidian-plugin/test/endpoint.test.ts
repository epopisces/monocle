import { describe, expect, it } from "vitest";
import { DEFAULT_COMPANION_ENDPOINT } from "@monocle/contracts";
import { parseCompanionEndpoint } from "@monocle/obsidian-plugin";

describe("companion endpoint setting", () => {
  it.each([
    ["http://127.0.0.1:48765", "http://127.0.0.1:48765"],
    ["  http://localhost:9000/  ", "http://localhost:9000"],
    ["http://[::1]:9000", "http://[::1]:9000"],
  ])("accepts loopback endpoint %j", (input, expected) => {
    expect(parseCompanionEndpoint(input)).toEqual({ ok: true, endpoint: expected });
  });

  it("falls back to the default endpoint when empty", () => {
    expect(parseCompanionEndpoint("")).toEqual({ ok: true, endpoint: DEFAULT_COMPANION_ENDPOINT });
  });

  it.each([
    ["http://192.168.1.10:48765", /loopback/],
    ["https://127.0.0.1:48765", /http:/],
    ["http://127.0.0.1:48765/api", /path/],
    ["not a url", /valid URL/],
  ])("rejects %j", (input, error) => {
    const result = parseCompanionEndpoint(input);
    expect(result.ok).toBe(false);
    expect(!result.ok && result.error).toMatch(error);
  });
});
