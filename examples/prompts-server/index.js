#!/usr/bin/env node
// Extended illustrative MCP-like server with a simple prompt template registry.

import { createInterface } from 'node:readline';
import { stdin as input, stdout as output } from 'node:process';
import Mustache from 'mustache';
import { z } from 'zod';

const tools = {
  markdown_summary: {
    description: 'Summarize a block of markdown text (simulated)',
    schema: z.object({ content: z.string().min(1) }),
    handler: async ({ content }) => ({ summary: content.split(/\s+/).slice(0, 12).join(' ') + '...' })
  }
};

const promptTemplates = {
  'qa/basic': {
    description: 'Simple Q&A wrapper',
    inputSchema: z.object({ question: z.string(), context: z.string().optional() }),
    template: 'You are a helpful system. Answer the user question.\nContext: {{context}}\nQuestion: {{question}}\nAnswer:'
  },
  'refactor/function': {
    description: 'Refactor function prompt',
    inputSchema: z.object({ code: z.string(), goal: z.string() }),
    template: 'Refactor the following code to achieve: {{goal}}\n\nCode:\n{{code}}\n\nRefactored:'
  }
};

function send(obj) { output.write(JSON.stringify(obj) + '\n'); }

function listCapabilities() {
  return {
    tools: Object.entries(tools).map(([name, t]) => ({ name, description: t.description })),
    prompts: Object.entries(promptTemplates).map(([name, p]) => ({ name, description: p.description }))
  };
}

async function handleRequest(msg) {
  const { id, method, params } = msg;
  try {
    switch (method) {
      case 'capability.list':
        return send({ jsonrpc: '2.0', id, result: listCapabilities() });
      case 'tool.call': {
        const { name, arguments: args } = params || {};
        const tool = tools[name];
        if (!tool) throw new Error(`Unknown tool: ${name}`);
        const parsed = tool.schema.parse(args);
        const result = await tool.handler(parsed);
        return send({ jsonrpc: '2.0', id, result });
      }
      case 'prompts.list': {
        return send({ jsonrpc: '2.0', id, result: Object.entries(promptTemplates).map(([name, p]) => ({ name, description: p.description })) });
      }
      case 'prompts.build': {
        const { name, variables } = params || {};
        const p = promptTemplates[name];
        if (!p) throw new Error(`Unknown prompt: ${name}`);
        const parsed = p.inputSchema.parse(variables || {});
        const rendered = Mustache.render(p.template, parsed);
        return send({ jsonrpc: '2.0', id, result: { prompt: rendered } });
      }
      default:
        throw new Error('Method not found');
    }
  } catch (e) {
    return send({ jsonrpc: '2.0', id, error: { code: -32000, message: e.message } });
  }
}

createInterface({ input }).on('line', (line) => {
  if (!line.trim()) return;
  try { handleRequest(JSON.parse(line)); }
  catch { send({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'Parse error' } }); }
});

send({ notice: 'Prompts server ready' });
