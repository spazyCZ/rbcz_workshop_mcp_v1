#!/usr/bin/env python3
"""Minimal illustrative MCP-like server in Python (stdio JSON-RPC style).

Implements two methods:
  - capability.list
  - tool.call (tools: echo, add)

This is an educational mock and not a full MCP implementation.
"""
import json
import sys


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


TOOLS = {
    "echo": {
        "description": "Echo back a message",
        "schema": {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]},
    },
    "add": {
        "description": "Add two numbers",
        "schema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    },
}


def list_capabilities():
    return {"tools": [{"name": name, "description": t["description"], "inputSchema": t["schema"]} for name, t in TOOLS.items()]}


def handle_tool_call(params):
    name = params.get("name") if params else None
    args = params.get("arguments") if params else None
    if name not in TOOLS:
        raise ValueError(f"Unknown tool: {name}")
    if name == "echo":
        message = args.get("message") if isinstance(args, dict) else None
        if not isinstance(message, str):
            raise ValueError("'message' must be string")
        return {"echoed": message, "length": len(message)}
    if name == "add":
        try:
            a = float(args.get("a"))
            b = float(args.get("b"))
        except Exception as e:  # noqa
            raise ValueError("'a' and 'b' must be numbers") from e
        return {"sum": a + b}
    raise ValueError("Unhandled tool")


def main():
    send({"notice": "Python simple demo server ready. Send JSON-RPC lines."})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        _id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params")
        try:
            if method == "capability.list":
                send({"jsonrpc": "2.0", "id": _id, "result": list_capabilities()})
            elif method == "tool.call":
                result = handle_tool_call(params)
                send({"jsonrpc": "2.0", "id": _id, "result": result})
            else:
                send({"jsonrpc": "2.0", "id": _id, "error": {"code": -32601, "message": "Method not found"}})
        except Exception as exc:  # noqa
            send({"jsonrpc": "2.0", "id": _id, "error": {"code": -32000, "message": str(exc)}})


if __name__ == "__main__":
    main()