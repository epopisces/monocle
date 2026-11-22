#!/usr/bin/env node
// Minimal MCP stdio server for Cravat adapter tests: tools `echo` and `hidden`.
import { createInterface } from "node:readline";

const send = (m) => process.stdout.write(`${JSON.stringify(m)}\n`);
for await (const line of createInterface({ input: process.stdin })) {
  if (!line.trim()) continue;
  const msg = JSON.parse(line);
  if (msg.method === "initialize") {
    send({ jsonrpc: "2.0", id: msg.id, result: { protocolVersion: msg.params.protocolVersion, capabilities: { tools: {} }, serverInfo: { name: "fake", version: "0" } } });
  } else if (msg.method === "tools/list") {
    const tool = (name) => ({ name, inputSchema: { type: "object" } });
    send({ jsonrpc: "2.0", id: msg.id, result: { tools: [tool("echo"), tool("hidden")] } });
  } else if (msg.method === "tools/call") {
    const text = `${msg.params.name}:${JSON.stringify(msg.params.arguments)}:${process.env.FAKE_MCP_TAG ?? ""}`;
    send({ jsonrpc: "2.0", id: msg.id, result: { content: [{ type: "text", text }] } });
  } else if (msg.id !== undefined) {
    send({ jsonrpc: "2.0", id: msg.id, error: { code: -32601, message: "method not found" } });
  }
}
