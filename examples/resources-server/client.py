#!/usr/bin/env python3
"""Simple client for resources-server (JSON-RPC over stdio).

Usage:
  python client.py list           # List available resources
  python client.py read <name>    # Read resource by name
"""
import sys
import json
import subprocess
import os

SERVER_PATH = os.path.join(os.path.dirname(__file__), "server.py")


def send_request(proc, method, params=None, _id=1):
    req = {"jsonrpc": "2.0", "id": _id, "method": method}
    if params is not None:
        req["params"] = params
    proc.stdin.write((json.dumps(req) + "\n").encode())
    proc.stdin.flush()
    # Read lines until we get a valid JSON-RPC response
    while True:
        line = proc.stdout.readline()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        # Only return if it's a JSON-RPC response with 'result' or 'error'
        if isinstance(obj, dict) and obj.get("jsonrpc") == "2.0" and ("result" in obj or "error" in obj):
            return obj


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("list", "read"):
        print("Usage: python client.py list | read <name>")
        sys.exit(1)
    proc = subprocess.Popen([
        sys.executable, SERVER_PATH
    ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Initialize
    resp = send_request(proc, "initialize")
    print("Server info:", resp.get("result"))

    # List capabilities
    resp = send_request(proc, "capability.list")
    print("Capabilities:", resp.get("result"))

    if sys.argv[1] == "list":
        resp = send_request(proc, "resources.list")
        print("Resources:")
        for item in resp.get("result", []):
            print(f"- {item['name']} ({item['mime']}, {item['size']} bytes)")
    elif sys.argv[1] == "read":
        if len(sys.argv) < 3:
            print("Usage: python client.py read <name>")
            sys.exit(1)
        name = sys.argv[2]
        resp = send_request(proc, "resources.read", {"name": name})
        result = resp.get("result")
        if result:
            print(f"Content of {name}:")
            print(result["content"])
        else:
            print("Error:", resp.get("error"))
    # Shutdown
    send_request(proc, "shutdown")
    proc.stdin.close()
    proc.stdout.close()
    proc.stderr.close()
    proc.wait()

if __name__ == "__main__":
    main()
