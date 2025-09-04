"""Simple LangGraph-style agent integrating local MCP-like subprocess servers.

This demonstrates how you could wrap the example servers found in:
  - examples/resources-server/server.py
  - examples/tools-server/server.py
  - examples/prompts-server/server.py

We spin each up as an on-demand subprocess (invoked per request for simplicity; a
production approach would keep them warm or manage a pool) and expose minimal
Python call helpers that look like *tools* inside a tiny LangGraph graph.

Because this workshop repo intentionally avoids external dependencies, we code
the graph logic in a style *compatible* with LangGraph concepts without pulling
an actual LLM provider. If you install `langgraph` and `langchain-core` (see
added requirements comments) this file should adapt easily—places marked with
`LLM PLACEHOLDER` show where you'd drop in a real model call.

Run:
  python examples/agent_simple/agent_1.py "Summarize the intro resource"
  python examples/agent_simple/agent_1.py "Reverse the phrase Hello World"

The agent will:
  1. Classify intent (resource question, prompt usage, or text tool op).
  2. If asking to summarize/improve, fetch the prompt template via prompts-server.
  3. If referencing a resource (by filename token like intro.md / guide.md / 'intro'),
	 it will fetch the resource content.
  4. If asking to echo / reverse, it will call the appropriate tool via tools-server.
  5. Produce a synthesized textual answer (heuristic, not a real LLM) combining
	 prompt instructions and resource content.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
RESOURCES_SERVER = ROOT / "resources-server" / "server.py"
TOOLS_SERVER = ROOT / "tools-server" / "server.py"
PROMPTS_SERVER = ROOT / "prompts-server" / "server.py"


# --------------------------- Subprocess JSON-RPC Client ---------------------------

class JsonRpcSubprocess:
	"""Minimal single-request helper (starts server per call for simplicity).

	Each request sequence: spawn -> initialize -> method call -> shutdown.
	For multi-call sessions, you could keep process open; kept simple here.
	"""

	def __init__(self, path: Path):
		self.path = path

	def _spawn(self):
		return subprocess.Popen(
			[sys.executable, str(self.path)],
			stdin=subprocess.PIPE,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			text=True,
		)

	def _send(self, proc, obj):
		assert proc.stdin is not None
		proc.stdin.write(json.dumps(obj) + "\n")
		proc.stdin.flush()

	def _recv_response(self, proc, want_id):
		assert proc.stdout is not None
		while True:
			line = proc.stdout.readline()
			if not line:
				raise RuntimeError("Server terminated unexpectedly")
			try:
				msg = json.loads(line)
			except Exception:
				continue
			if msg.get("jsonrpc") == "2.0" and msg.get("id") == want_id:
				return msg

	def call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
		proc = self._spawn()
		try:
			# initialize (id 0)
			self._send(proc, {"jsonrpc": "2.0", "id": 0, "method": "initialize"})
			self._recv_response(proc, 0)
			# actual call (id 1)
			self._send(
				proc,
				{"jsonrpc": "2.0", "id": 1, "method": method, **({"params": params} if params else {})},
			)
			resp = self._recv_response(proc, 1)
			if "error" in resp:
				raise RuntimeError(resp["error"])  # propagate
			return resp.get("result")
		finally:
			# shutdown politely
			try:
				self._send(proc, {"jsonrpc": "2.0", "id": 2, "method": "shutdown"})
			except Exception:
				pass
			try:
				proc.terminate()
			except Exception:
				pass


resources_client = JsonRpcSubprocess(RESOURCES_SERVER)
tools_client = JsonRpcSubprocess(TOOLS_SERVER)
prompts_client = JsonRpcSubprocess(PROMPTS_SERVER)


# --------------------------- Agent State & Utilities ---------------------------

@dataclass
class AgentState:
	query: str
	reasoning: List[str] = field(default_factory=list)
	resources_used: List[str] = field(default_factory=list)
	tool_calls: List[Dict[str, Any]] = field(default_factory=list)
	prompt_used: Optional[str] = None
	answer: Optional[str] = None

	def log(self, msg: str):
		self.reasoning.append(msg)


RESOURCE_NAME_PATTERN = re.compile(r"(intro|guide)(?:\.md)?", re.IGNORECASE)


def classify_intent(q: str) -> str:
	ql = q.lower()
	if any(w in ql for w in ["summarize", "improve", "summary"]):
		return "prompt"
	if any(w in ql for w in ["echo", "reverse"]):
		return "tool"
	if RESOURCE_NAME_PATTERN.search(ql):
		return "resource"
	# fall back: if mentions resource words treat as resource
	return "resource"


def fetch_resource_names() -> List[str]:
	try:
		items = resources_client.call("resources.list")
		return [i["name"] for i in items]
	except Exception:
		return []


def read_resource(name: str) -> str:
	result = resources_client.call("resources.read", {"name": name})
	return result.get("content", "")


def call_tool(name: str, text: str) -> str:
	result = tools_client.call(
		"tools.call", {"name": name, "arguments": {"text": text}}
	)
	# server returns { content: [ {type: text, text: ...} ] }
	content = result.get("content", [])
	if content and isinstance(content, list):
		return content[0].get("text", "")
	return ""


def get_prompt(name: str, text: str) -> List[Dict[str, str]]:
	prompt = prompts_client.call("prompts.get", {"name": name})
	messages = []
	for m in prompt.get("messages", []):
		content = m.get("content", "").replace("{{text}}", text)
		messages.append({"role": m.get("role", "user"), "content": content})
	return messages


# --------------------------- Core Agent Logic (Pseudo LangGraph) ---------------

def agent_run(query: str) -> AgentState:
	state = AgentState(query=query)
	state.log(f"Received query: {query}")
	intent = classify_intent(query)
	state.log(f"Classified intent: {intent}")

	resource_text = ""
	if intent in ("resource", "prompt"):
		names = fetch_resource_names()
		chosen = None
		for n in names:
			if n.split(".")[0].lower() in query.lower():
				chosen = n
				break
		if not chosen and names:
			chosen = names[0]
		if chosen:
			state.log(f"Reading resource: {chosen}")
			try:
				resource_text = read_resource(chosen)
				state.resources_used.append(chosen)
			except Exception as exc:
				state.log(f"Failed to read resource {chosen}: {exc}")

	tool_output = ""
	if intent == "tool":
		# choose echo or reverse
		if "reverse" in query.lower():
			tool = "reverse"
		else:
			tool = "echo"
		state.log(f"Calling tool: {tool}")
		try:
			tool_output = call_tool(tool, query)
			state.tool_calls.append({"name": tool, "input": query, "output": tool_output})
		except Exception as exc:
			state.log(f"Tool call failed: {exc}")

	prompt_messages: List[Dict[str, str]] = []
	if intent == "prompt":
		# pick prompt by verb
		if "improve" in query.lower():
			prompt_name = "improve"
		else:
			prompt_name = "summarize"
		state.log(f"Using prompt template: {prompt_name}")
		state.prompt_used = prompt_name
		source_text = resource_text or query
		try:
			prompt_messages = get_prompt(prompt_name, source_text)
		except Exception as exc:
			state.log(f"Prompt retrieval failed: {exc}")

	# LLM PLACEHOLDER: Compose a deterministic "answer"
	parts = []
	if prompt_messages:
		sys_msg = next((m["content"] for m in prompt_messages if m["role"] == "system"), "")
		user_msg = next((m["content"] for m in prompt_messages if m["role"] == "user"), "")
		parts.append(f"[Prompt System]\n{sys_msg}\n")
		parts.append(f"[Prompt User]\n{user_msg}\n")
	if resource_text:
		parts.append("[Resource Excerpt]\n" + resource_text[:400] + ("..." if len(resource_text) > 400 else ""))
	if tool_output:
		parts.append(f"[Tool Output]\n{tool_output}")
	if not parts:
		parts.append("No external info used; responding heuristically.")
	# simplistic summarization / improvement heuristic
	if intent == "prompt" and "summarize" in query.lower():
		# crude: take first 3 sentences
		sentences = re.split(r"(?<=[.!?])\s+", resource_text or query)
		summary = " ".join(sentences[:3])
		parts.append(f"[Heuristic Summary]\n{summary}")
	elif intent == "prompt" and "improve" in query.lower():
		improved = re.sub(r"\butilize\b", "use", resource_text or query, flags=re.IGNORECASE)
		parts.append(f"[Heuristic Improvement]\n{improved}")
	elif intent == "tool":
		parts.append("Tool result returned above.")

	state.answer = "\n\n".join(parts)
	state.log("Answer composed.")
	return state


def main(argv: List[str]):
	if len(argv) < 2:
		print("Usage: python agent_1.py <query>")
		return 1
	query = " ".join(argv[1:])
	state = agent_run(query)
	print("=== Agent Reasoning ===")
	for step in state.reasoning:
		print("-", step)
	print("\n=== Answer ===\n" + (state.answer or "<no answer>"))
	return 0


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(main(sys.argv))

