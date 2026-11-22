/** Monocle for Obsidian. Talks to the companion only through @monocle/contracts. */
import { CONTRACT_VERSION, type PackageDescriptor } from "@monocle/contracts";

export const packageDescriptor: PackageDescriptor = {
  name: "@monocle/obsidian-plugin",
  role: "client",
  contractVersion: CONTRACT_VERSION,
};
