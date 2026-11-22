/** Monocle for Obsidian. Talks to the companion only through @monocle/contracts. */
import { CONTRACT_VERSION, type PackageDescriptor } from "@monocle/contracts";

export {
  CompanionConnection,
  type CompanionConnectionOptions,
  type ConnectionState,
  type HealthProbe,
} from "./connection.js";
export { parseCompanionEndpoint, type EndpointResult } from "./endpoint.js";
export { ConversationClient, type ConversationClientOptions } from "./conversation-client.js";
export {
  IndexHealthMonitor,
  type ActionResult,
  type CompanionRequest,
  type IndexHealthMonitorOptions,
  type IndexView,
} from "./index-health.js";
export {
  ExecutionClient,
  type ExecuteOptions,
  type ExecutionClientOptions,
  type ExecutionHandle,
  type FetchLike,
} from "./execution-client.js";

export const packageDescriptor: PackageDescriptor = {
  name: "@monocle/obsidian-plugin",
  role: "client",
  contractVersion: CONTRACT_VERSION,
};
