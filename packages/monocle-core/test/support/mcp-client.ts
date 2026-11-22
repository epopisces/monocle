import { spawn, type ChildProcess } from "node:child_process";
import { createInterface } from "node:readline";

export interface ToolResult {
  isError?: boolean;
  content: { type: string; text: string }[];
}

/** Minimal MCP stdio client for tests: newline-delimited JSON-RPC, as the Copilot CLI speaks it. */
export class McpTestClient {
  private readonly child: ChildProcess;
  private nextId = 1;
  private readonly pending = new Map<number, (msg: { result?: unknown; error?: { message: string } }) => void>();

  constructor(command: string, args: readonly string[]) {
    this.child = spawn(command, args, { stdio: ["pipe", "pipe", "inherit"] });
    createInterface({ input: this.child.stdout! }).on("line", (line) => {
      const msg = JSON.parse(line) as { id: number; result?: unknown; error?: { message: string } };
      this.pending.get(msg.id)?.(msg);
      this.pending.delete(msg.id);
    });
  }

  send(raw: string): void {
    this.child.stdin!.write(`${raw}\n`);
  }

  request<T = unknown>(method: string, params: unknown = {}): Promise<{ result?: T; error?: { message: string } }> {
    const id = this.nextId++;
    return new Promise((resolve) => {
      this.pending.set(id, resolve as never);
      this.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
    });
  }

  async initialize(): Promise<void> {
    await this.request("initialize", { protocolVersion: "2025-11-25", capabilities: {}, clientInfo: { name: "test", version: "0" } });
    this.send(JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }));
  }

  async call(name: string, args: Record<string, unknown>): Promise<ToolResult> {
    const res = await this.request<ToolResult>("tools/call", { name, arguments: args });
    if (!res.result) throw new Error(`tools/call failed: ${res.error?.message}`);
    return res.result;
  }

  close(): void {
    this.child.kill();
  }
}
