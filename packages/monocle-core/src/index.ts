/** Monocle knowledge services (read/search/index/validate/change). Implemented from M1 onward. */
import { CONTRACT_VERSION, type PackageDescriptor } from "@monocle/contracts";

export const packageDescriptor: PackageDescriptor = {
  name: "@monocle/core",
  role: "knowledge-services",
  contractVersion: CONTRACT_VERSION,
};

export * from "./note-index/note-index.js";
export * from "./note-index/watch.js";
export type { ExtractedLink, LinkKind, SourceLocation } from "./note-index/links.js";
export type { LinkMatch, LinkStatus, NoteLink, NoteRef } from "./note-index/relationships.js";
export type { NoteFilter } from "./note-index/metadata.js";
