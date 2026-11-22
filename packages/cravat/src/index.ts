/** Cravat agent execution and provider adapters. Must not depend on Monocle knowledge services. */
import { CONTRACT_VERSION, type PackageDescriptor } from "@monocle/contracts";

export {
  ExecutionManager,
  ProviderError,
  type Execution,
  type ExecutionManagerOptions,
  type ExecutionToolset,
  type McpToolServer,
  type ProviderRunOptions,
  type StartOptions,
  type ProviderAdapter,
  type ProviderEvent,
} from "./execution-manager.js";
export { CopilotCliAdapter, type CopilotCliAdapterOptions } from "./copilot-cli-adapter.js";

export const packageDescriptor: PackageDescriptor = {
  name: "@monocle/cravat",
  role: "execution",
  contractVersion: CONTRACT_VERSION,
};
