"""HTTP wrapper for the MCP example tools server.

Exposes the functionality in `server.py` via a simple REST API using FastAPI.

Endpoints:
  GET /health            -> {"status": "ok"}
  GET /capabilities      -> returns same structure as initialize()["capabilities"]
  GET /tools             -> list available tools
  POST /invoke           -> body: {"name": "echo", "arguments": {"text": "hi"}}
  POST /tools/{name}     -> body: {"arguments": {"text": "hi"}}

Responses follow a light-weight JSON shape and do NOT wrap in JSON-RPC; this is
intended as a human and demo friendly facade.

Run:
  python web_server_wrapper.py  (uses uvicorn programmatically) OR
  uvicorn web_server_wrapper:app --reload
"""

from __future__ import annotations

import os
import importlib.util
import pathlib
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict

# Load sibling server.py via spec so we don't rely on an importable package name
# (the folder name contains a hyphen making normal imports invalid).
_HERE = pathlib.Path(__file__).parent
_SERVER_PATH = _HERE / "server.py"
_SPEC = importlib.util.spec_from_file_location("tools_server_core", _SERVER_PATH)
core = importlib.util.module_from_spec(_SPEC)  # type: ignore
assert _SPEC and _SPEC.loader, "Failed to create spec for core server module"
_SPEC.loader.exec_module(core)  # type: ignore

app = FastAPI(title="MCP Tools Server Wrapper", version="0.1.0")


class InvokeRequest(BaseModel):
    name: str = Field(..., description="Tool name to invoke")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments matching the tool input schema")


class ToolInvokeRequest(BaseModel):
    arguments: Dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/capabilities")
def get_capabilities():
    return core.list_capabilities()


@app.get("/tools")
def list_tools():
    return core.tools_list()


@app.post("/invoke")
def invoke(req: InvokeRequest):
    try:
        result = core.tools_call({"name": req.name, "arguments": req.arguments})
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve)) from ve
    except Exception as exc:  # pragma: no cover - generic safety
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result


@app.post("/tools/{name}")
def invoke_tool(name: str, req: ToolInvokeRequest):
    try:
        result = core.tools_call({"name": name, "arguments": req.arguments})
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve)) from ve
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result


@app.get("/")
def root():
    return {
        "name": core.initialize(None)["name"],
        "version": core.initialize(None)["version"],
        "endpoints": [
            "/", "/health", "/capabilities", "/tools", "POST /invoke", "POST /tools/{name}"
        ],
    }


def run():
    """Programmatic entrypoint so users can `python web_server_wrapper.py`."""
    host = os.environ.get("TOOLS_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("TOOLS_SERVER_PORT", "8001"))
    uvicorn.run(app, host=host, port=port, reload=bool(os.environ.get("RELOAD")))


if __name__ == "__main__":  # pragma: no cover
    run()
