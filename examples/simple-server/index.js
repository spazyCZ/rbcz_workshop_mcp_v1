#!/usr/bin/env node
// Minimal illustrative MCP-like server (conceptual) - does not rely on a published SDK.
// For workshop purposes: shows shape of messages (JSON-RPC style) over stdio.

import { createInterface } from 'node:readline';
import { stdin as input, stdout as output } from 'node:process';
import { ZodError, z } from 'zod';

// Tool registry
const tools = {
  echo: {
    description: 'Echo back a message',
    schema: z.object({ message: z.string() }),
    handler: async ({ message }) => ({ echoed: message, length: message.length })
  },
  add: {
    description: 'Add two numbers',
    schema: z.object({ a: z.number(), b: z.number() }),
    handler: async ({ a, b }) => ({ sum: a + b })
  }
};

let nextId = 1;

function send(obj) {
  output.write(JSON.stringify(obj) + '\n');
}

function listCapabilities() {
  return Object.entries(tools).map(([name, t]) => ({
    name,
    description: t.description,
    inputSchema: JSON.parse(t.schema.toString ? '{}': '{}') // Placeholder for workshop; real SDK would expose JSON Schema
  }));
}

async function handleRequest(message) {
  const { id, method, params } = message;
  try {
    if (method === 'capability.list') {
      return send({ jsonrpc: '2.0', id, result: { tools: listCapabilities() } });
    }
    if (method === 'tool.call') {
      const { name, arguments: args } = params || {};
      const tool = tools[name];
      if (!tool) throw new Error(`Unknown tool: ${name}`);
      const parsed = tool.schema.parse(args);
      const result = await tool.handler(parsed);
      return send({ jsonrpc: '2.0', id, result });
    }
    throw new Error('Method not found');
  } catch (err) {
    if (err instanceof ZodError) {
      return send({ jsonrpc: '2.0', id, error: { code: -32602, message: 'Invalid params', data: err.errors } });
    }
    return send({ jsonrpc: '2.0', id, error: { code: -32000, message: err.message } });
  }
}

const rl = createInterface({ input });
rl.on('line', (line) => {
  if (!line.trim()) return;
  let msg;
  try { msg = JSON.parse(line); } catch (e) {
    return send({ jsonrpc: '2.0', id: nextId++, error: { code: -32700, message: 'Parse error' } });
  }
  handleRequest(msg);
});

// Send an initial banner (out-of-band) for human debugging
send({ notice: 'MCP simple demo server ready. Send JSON-RPC lines.' });
