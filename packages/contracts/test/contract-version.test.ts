import { describe, expect, it } from "vitest";
import { CONTRACT_VERSION, isContractCompatible } from "@monocle/contracts";

describe("contract version compatibility", () => {
  it("accepts a peer on the same major version with an equal or older minor", () => {
    expect(isContractCompatible({ local: "1.4.0", remote: "1.2.9" })).toBe(true);
    expect(isContractCompatible({ local: "1.4.0", remote: "1.4.0" })).toBe(true);
  });

  it("rejects a peer that requires a newer minor than the local side provides", () => {
    expect(isContractCompatible({ local: "1.2.0", remote: "1.3.0" })).toBe(false);
  });

  it("rejects a different major version", () => {
    expect(isContractCompatible({ local: "2.0.0", remote: "1.9.0" })).toBe(false);
  });

  it("treats 0.x minors as breaking, per semver", () => {
    expect(isContractCompatible({ local: "0.2.0", remote: "0.1.0" })).toBe(false);
    expect(isContractCompatible({ local: "0.1.3", remote: "0.1.0" })).toBe(true);
  });

  it("rejects malformed versions instead of guessing", () => {
    expect(isContractCompatible({ local: "1.0", remote: "1.0.0" })).toBe(false);
    expect(isContractCompatible({ local: "1.0.0", remote: "latest" })).toBe(false);
  });

  it("publishes a well-formed contract version", () => {
    expect(isContractCompatible({ local: CONTRACT_VERSION, remote: CONTRACT_VERSION })).toBe(true);
  });
});
