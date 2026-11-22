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
export * from "./vault-tools/vault-reader.js";
export * from "./vault-tools/tools.js";
export * from "./vault-tools/mcp-server.js";
export * from "./conversations/conversation-store.js";
export * from "./index-service.js";
export * from "./operations/validate-note.js";
export type { ExtractedLink, LinkKind, SourceLocation } from "./note-index/links.js";
export type { LinkMatch, LinkStatus, NoteLink, NoteRef } from "./note-index/relationships.js";
export type { NoteFilter } from "./note-index/metadata.js";
