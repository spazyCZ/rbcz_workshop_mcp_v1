#!/usr/bin/env python3
"""Illustrative MCP-like prompts server (Python).

Implements methods:
  - capability.list
  - prompts.list
  - prompts.get
"""
import json
import sys
import os


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def list_capabilities():
    return {
        "prompts": {
            "list": {"description": "List available prompt templates"},
            "get": {"description": "Get a prompt by name"},
        }
    }


PROMPTS = {
    "summarize": {
        "name": "summarize",
        "description": "Summarize provided text",
        "arguments": [
            {"name": "text", "description": "Input text to summarize", "required": True}
        ],
        "messages": [
            {"role": "system", "content": "You are a helpful summarization assistant."},
            {"role": "user", "content": "{{text}}"},
        ],
    },
    "improve": {
        "name": "improve",
        "description": "Improve clarity and grammar of text",
        "arguments": [
            {"name": "text", "description": "Draft text to improve", "required": True}
        ],
        "messages": [
            {"role": "system", "content": "You refine user text for clarity and correctness."},
            {"role": "user", "content": "{{text}}"},
        ],
    },
}


def prompts_list():
    return [
        {"name": p["name"], "description": p["description"], "arguments": p["arguments"]}
        for p in PROMPTS.values()
    ]


def prompts_get(params):
    name = (params or {}).get("name")
    if name not in PROMPTS:
        raise ValueError(f"Unknown prompt: {name}")
    return PROMPTS[name]


def initialize(_params):
    return {
        "name": "prompts-server",
        "version": "0.1.0",
        "capabilities": list_capabilities()
    }


def shutdown(_params):
    return {"ok": True}


METHOD_ALIASES = {
    "capabilities.list": "capability.list"
}


def main():
    send({"notice": "Python prompts server ready (methods: initialize, capability.list, prompts.list, prompts.get)"})
    debug = bool(os.environ.get("PROMPTS_SERVER_DEBUG"))
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        method = msg.get("method")
        params = msg.get("params")
        _id = msg.get("id")
        original_method = method
        if method in METHOD_ALIASES:
            method = METHOD_ALIASES[method]
        try:
            if debug:
                send({"debug": {"received": original_method, "normalized": method}})
            if method == "initialize":
                send({"jsonrpc":"2.0","id":_id,"result": initialize(params)})
            elif method == "shutdown":
                send({"jsonrpc":"2.0","id":_id,"result": shutdown(params)})
                continue
            elif method == "capability.list":
                send({"jsonrpc":"2.0","id":_id,"result": list_capabilities()})
            elif method == "prompts.list":
                send({"jsonrpc":"2.0","id":_id,"result": prompts_list()})
            elif method == "prompts.get":
                send({"jsonrpc":"2.0","id":_id,"result": prompts_get(params)})
            else:
                send({"jsonrpc":"2.0","id":_id,"error":{"code":-32601,"message": f"Method not found: {original_method}"}})
        except Exception as exc:
            send({"jsonrpc":"2.0","id":_id,"error":{"code":-32000,"message":str(exc)}})


if __name__ == "__main__":
    main()