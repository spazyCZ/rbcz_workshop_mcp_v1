#!/usr/bin/env python3
import json, sys, os

def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

def list_capabilities():
    return {
        "tools": {
            "list": {"description": "List available tools"},
            "call": {"description": "Invoke a tool by name"}
        }
    }

BASE_INPUT_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

def _tool(name, description):
    # Provide both snake_case and camelCase until the spec stabilizes.
    return {
        "name": name,
        "description": description,
        "input_schema": BASE_INPUT_SCHEMA,
        "inputSchema": BASE_INPUT_SCHEMA,
    }

TOOLS = {
    "echo": _tool("echo", "Echo back the provided text"),
    "reverse": _tool("reverse", "Reverse the provided text")
}

def initialize(_params):
    return {
        "name": "tools-server",
        "version": "0.1.0",
        "protocolVersion": "2024-09-01",  # indicative protocol version string
        "capabilities": list_capabilities()
    }

def shutdown(_params):
    return {"ok": True}

# Canonical method names follow plural 'capabilities' and dotted or slash variants.
METHOD_ALIASES = {
    # Legacy singular -> plural
    "capability.list": "capabilities.list",
    # Slash style variants
    "capabilities/list": "capabilities.list",
    "tools/list": "tools.list",
    "tools/call": "tools.call",
    # Alternate invocation verbs
    "tools.invoke": "tools.call",
    "tools.execute": "tools.call"
}

def tools_list():
    # Future: could filter by capabilities, categories, etc.
    return list(TOOLS.values())

def tools_call(params):
    name = (params or {}).get("name")
    arguments = (params or {}).get("arguments") or {}
    if name not in TOOLS:
        raise ValueError(f"Unknown tool: {name}")
    if "text" not in arguments:
        raise ValueError("Missing required argument: 'text'")
    text = arguments.get("text")
    if name == "echo":
        output = text
    elif name == "reverse":
        output = text[::-1]
    else:
        output = ""
    return {"content": [{"type": "text", "text": output}]}

def main():
    # Send human-readable startup info to stderr so stdout is purely protocol.
    # Some hosts (e.g. VS Code log viewers) may classify any stderr line as a warning.
    # To allow turning this off, honor environment variables:
    #   TOOLS_SERVER_SUPPRESS_STARTUP / TOOLS_SERVER_QUIET -> do not print banner
    #   TOOLS_SERVER_STARTUP_STDOUT -> print banner to stdout (useful for debugging)
    suppress_banner = os.environ.get("TOOLS_SERVER_SUPPRESS_STARTUP") or os.environ.get("TOOLS_SERVER_QUIET")
    banner_to_stdout = os.environ.get("TOOLS_SERVER_STARTUP_STDOUT")
    banner = "[tools-server] ready (methods: initialize, capabilities.list, tools.list, tools.call)"
    if not suppress_banner:
        if banner_to_stdout:
            # Still flush immediately so clients reading line-buffered logs see it.
            print(banner)
            sys.stdout.flush()
        else:
            print(banner, file=sys.stderr)
            sys.stderr.flush()
    debug = bool(os.environ.get("TOOLS_SERVER_DEBUG"))
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            send({"jsonrpc": "2.0","id": None,"error":{"code": -32700,"message":"Parse error"}})
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
            elif method == "capabilities.list":
                send({"jsonrpc": "2.0","id": _id,"result": list_capabilities()})
            elif method == "tools.list":
                send({"jsonrpc": "2.0","id": _id,"result": tools_list()})
            elif method == "tools.call":
                send({"jsonrpc": "2.0","id": _id,"result": tools_call(params)})
            else:
                send({"jsonrpc": "2.0","id": _id,"error":{"code": -32601,"message": f"Method not found: {original_method}"}})
        except Exception as exc:
            send({"jsonrpc": "2.0","id": _id,"error":{"code": -32000,"message": str(exc)}})

if __name__ == "__main__":
    main()
