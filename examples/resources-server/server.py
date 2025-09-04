#!/usr/bin/env python3
"""Resource example MCP-like server (stdio JSON-RPC style).

Implements:
  - capability.list (announces resources capability)
  - resources.list (enumerate resource metadata)
  - resources.read (fetch resource content by name)

This keeps the pattern consistent with other workshop examples and is intentionally
minimal (no pagination, mime sniffing, or streaming).
"""
import json
import sys
import os
from pathlib import Path

ROOT = Path(__file__).parent / "resources"


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def list_capabilities():
    return {
        "resources": {
            "list": {"description": "List available resource documents"},
            "read": {"description": "Read a resource by name"},
            "get": {"description": "Get metadata for a single resource by name"},
        }
    }


def resources_list():
    items = []
    for p in sorted(ROOT.glob("*")):
        if p.is_file():
            items.append(
                {
                    "name": p.name,
                    "mime": "text/markdown" if p.suffix == ".md" else "text/plain",
                    "size": p.stat().st_size,
                    "description": f"Resource file {p.name}",
                }
            )
    return items


def resources_read(params):
    name = (params or {}).get("name")
    if not name:
        raise ValueError("Missing 'name'")
    target = ROOT / name
    if not target.is_file():
        raise ValueError(f"Unknown resource: {name}")
    content = target.read_text(encoding="utf-8")
    return {"name": name, "content": content}


def resources_get(params):
    """Return metadata for a single resource (no content)."""
    name = (params or {}).get("name")
    if not name:
        raise ValueError("Missing 'name'")
    target = ROOT / name
    if not target.is_file():
        raise ValueError(f"Unknown resource: {name}")
    return {
        "name": target.name,
        "mime": "text/markdown" if target.suffix == ".md" else "text/plain",
        "size": target.stat().st_size,
        "description": f"Resource file {target.name}",
    }


METHOD_ALIASES = {
    "capabilities.list": "capability.list"
}


def initialize(_params):
    # Return a simple server description + capabilities (mirrors capability.list)
    return {
        "name": "resources-server",
        "version": "0.1.0",
        "capabilities": list_capabilities()
    }


def shutdown(_params):
    return {"ok": True}


def main():
    send({"notice": "Python resources server ready"})
    debug = bool(os.environ.get("RESOURCES_SERVER_DEBUG"))
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
        if method in METHOD_ALIASES:
            method = METHOD_ALIASES[method]
        try:
            if method == "initialize":
                send({"jsonrpc": "2.0", "id": _id, "result": initialize(params)})
            elif method == "shutdown":
                send({"jsonrpc": "2.0", "id": _id, "result": shutdown(params)})
                # After responding to shutdown we can break (optional)
                continue
            elif method == "capability.list":
                send({"jsonrpc": "2.0", "id": _id, "result": list_capabilities()})
            elif method == "resources.list":
                send({"jsonrpc": "2.0", "id": _id, "result": resources_list()})
            elif method == "resources.get":
                send({"jsonrpc": "2.0", "id": _id, "result": resources_get(params)})
            elif method == "resources.read":
                result = resources_read(params)
                send({"jsonrpc": "2.0", "id": _id, "result": result})
            else:
                send({"jsonrpc": "2.0", "id": _id, "error": {"code": -32601, "message": f"Method not found: {method}"}})
            if debug:
                send({"debug": {"handled": method}})
        except Exception as exc:  # noqa
            send({"jsonrpc": "2.0", "id": _id, "error": {"code": -32000, "message": str(exc)}})


if __name__ == "__main__":
    main()
