/**
 * Version of the inter-package contract surface exported here. Peers (plugin ↔ companion,
 * companion ↔ modules) compare versions with {@link isContractCompatible}.
 */
export const CONTRACT_VERSION = "0.1.0";

export * from "./companion.js";
export * from "./index-health.js";

const SEMVER = /^(\d+)\.(\d+)\.(\d+)$/;

function parse(version: string): [number, number, number] | undefined {
  const m = SEMVER.exec(version);
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : undefined;
}

/**
 * True when a `local` implementation can serve a `remote` peer that was built against
 * `remote`'s contract version. Semver rules: same major, local minor ≥ remote minor;
 * for 0.x versions the minor is treated as the breaking component.
 */
export function isContractCompatible(versions: { local: string; remote: string }): boolean {
  const local = parse(versions.local);
  const remote = parse(versions.remote);
  if (!local || !remote) return false;
  const [lMaj, lMin] = local;
  const [rMaj, rMin] = remote;
  if (lMaj !== rMaj) return false;
  if (lMaj === 0) return lMin === rMin;
  return lMin >= rMin;
}

export type PackageRole = "contracts" | "knowledge-services" | "execution" | "companion" | "client";

/** Self-description every workspace package exports as `packageDescriptor`. */
export interface PackageDescriptor {
  readonly name: string;
  readonly role: PackageRole;
  /** Contract version the package was built against. */
  readonly contractVersion: string;
}

export const packageDescriptor: PackageDescriptor = {
  name: "@monocle/contracts",
  role: "contracts",
  contractVersion: CONTRACT_VERSION,
};
