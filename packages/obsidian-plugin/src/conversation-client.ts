import {
  CONVERSATIONS_PATH,
  conversationPath,
  type Conversation,
  type ConversationListResponse,
  type ConversationSummary,
} from "@monocle/contracts";
import type { FetchLike } from "./execution-client.js";

export interface ConversationClientOptions {
  readonly endpoint: string;
  readonly fetch: FetchLike;
}

/**
 * Reads the companion's machine-local conversation history. Obsidian-free so it is testable in Node. The plugin
 * never stores conversation content itself; it only remembers which conversation is open.
 */
export class ConversationClient {
  private readonly endpoint: string;
  private readonly fetch: FetchLike;

  constructor(options: ConversationClientOptions) {
    this.endpoint = options.endpoint;
    this.fetch = options.fetch;
  }

  /** Most recent first; `undefined` if the companion does not offer conversations (older companion). */
  async list(): Promise<readonly ConversationSummary[] | undefined> {
    const body = await this.getJson<ConversationListResponse>(CONVERSATIONS_PATH);
    return Array.isArray(body?.conversations) ? body.conversations : undefined;
  }

  /** `undefined` if the companion does not know the conversation. */
  async get(id: string): Promise<Conversation | undefined> {
    const body = await this.getJson<Conversation>(conversationPath(id));
    return body && Array.isArray(body.executions) ? body : undefined;
  }

  private async getJson<T>(path: string): Promise<T | undefined> {
    const res = await this.fetch(new URL(path, this.endpoint).href, { method: "GET" });
    if (res.status === 404) {
      await res.body?.cancel();
      return undefined;
    }
    if (!res.ok) throw new Error(`companion returned HTTP ${res.status}`);
    return (await res.json()) as T;
  }
}
