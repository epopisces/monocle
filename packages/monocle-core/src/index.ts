/** Monocle knowledge services (read/search/index/validate/change). Implemented from M1 onward. */
import { CONTRACT_VERSION, type PackageDescriptor } from "@monocle/contracts";

export const packageDescriptor: PackageDescriptor = {
  name: "@monocle/core",
  role: "knowledge-services",
  contractVersion: CONTRACT_VERSION,
};

export * from "./note-index/note-index.js";
export * from "./note-index/watch.js";
export * from "./semantic/chunk.js";
export * from "./semantic/types.js";
export * from "./semantic/memory-store.js";
export * from "./semantic/semantic-index.js";
export * from "./semantic/embedding-providers.js";
export * from "./semantic/chroma-store.js";
export * from "./semantic/config.js";
export * from "./semantic/retriever.js";
