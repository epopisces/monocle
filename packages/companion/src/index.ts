/** Local companion process hosting Monocle knowledge services and Cravat; lifecycle independent of Obsidian. */
import { CONTRACT_VERSION, type PackageDescriptor } from "@monocle/contracts";

export { startCompanion, type CompanionOptions, type RunningCompanion } from "./server.js";
export { type CompanionVaultOptions } from "./context.js";

export const packageDescriptor: PackageDescriptor = {
  name: "@monocle/companion",
  role: "companion",
  contractVersion: CONTRACT_VERSION,
};
