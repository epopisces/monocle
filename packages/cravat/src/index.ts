/** Cravat agent execution and provider adapters. Must not depend on Monocle knowledge services. */
import { CONTRACT_VERSION, type PackageDescriptor } from "@monocle/contracts";

export const packageDescriptor: PackageDescriptor = {
  name: "@monocle/cravat",
  role: "execution",
  contractVersion: CONTRACT_VERSION,
};
