/** Turns passages into vectors. Implementations: local Ollama (default), policy-gated OpenAI-compatible. */
export interface EmbeddingProvider {
  /** Model + version identity, e.g. `ollama:nomic-embed-text`. A change triggers a semantic rebuild. */
  readonly id: string;
  /** `remote` providers send note text off-host and must be permitted by policy. */
  readonly locality: "local" | "remote";
  embed(texts: string[]): Promise<number[][]>;
}

/** Metadata stored alongside each vector; links a passage to its note identity and content hashes. */
export interface PassageMetadata {
  path: string;
  noteId: string | null;
  /** SHA-256 of the note file when the passage was indexed. */
  noteHash: string;
  heading: string;
  ordinal: number;
  /** SHA-256 of the passage text. */
  textHash: string;
}

export interface VectorRecord {
  id: string;
  vector: number[];
  text: string;
  metadata: PassageMetadata;
}

export interface VectorMatch {
  id: string;
  /** Cosine distance; lower is closer. */
  distance: number;
  text: string;
  metadata: PassageMetadata;
}

/** Derived, rebuildable vector storage (never authoritative). Implementations: Chroma, in-memory. */
export interface VectorStore {
  /** Store identity (e.g. Chroma URL + collection). A change triggers a semantic rebuild. */
  readonly id: string;
  upsert(records: VectorRecord[]): Promise<void>;
  delete(ids: string[]): Promise<void>;
  query(vector: number[], limit: number): Promise<VectorMatch[]>;
  /** Drops every record. */
  reset(): Promise<void>;
}
