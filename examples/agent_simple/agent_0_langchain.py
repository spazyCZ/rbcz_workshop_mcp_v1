import os
import json
from typing import List
from dotenv import load_dotenv

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

load_dotenv()

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("Missing OPENAI_API_KEY in environment. Set it in your .env file.")

@tool
def reverse_text(text: str) -> str:
    """Return the reversed form of the input text."""
    if text is None:
        return "Error: 'text' argument is required."
    return text[::-1]

MODEL_NAME = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"

model = ChatOpenAI(
    model=MODEL_NAME,
    temperature=0,
    verbose=True
)

try:
    model_with_tools = model.bind_tools([reverse_text])
except NotImplementedError:
    model_with_tools = model


def call_with_tool(messages: List):
    ai_msg = model_with_tools.invoke(messages)
    yield ai_msg
    if isinstance(ai_msg, AIMessage) and getattr(ai_msg, 'tool_calls', None):
        tool_results = []
        for tc in ai_msg.tool_calls:
            if tc["name"] == "reverse_text":
                arg_text = tc["args"].get("text") or tc["args"].get("input") or tc["args"].get("value")
                if arg_text is None:
                    result = "Tool usage error: missing 'text' argument."
                else:
                    result = reverse_text.invoke({"text": arg_text})
                tool_results.append(ToolMessage(name=tc["name"], content=result, tool_call_id=tc["id"]))
        follow_messages = messages + [ai_msg] + tool_results
        final_ai = model_with_tools.invoke(follow_messages)
        yield from tool_results
        yield final_ai


def run(query: str):
    print(f"User: {query}")
    convo: List = [HumanMessage(content=query)]
    for m in call_with_tool(convo):
        if isinstance(m, AIMessage) and getattr(m, 'tool_calls', None):
            print("Model requested tool(s): " + ", ".join(f"{tc['name']}({json.dumps(tc['args'])})" for tc in m.tool_calls))
        elif isinstance(m, ToolMessage):
            print(f"[tool:{m.name}] {m.content}")
        elif isinstance(m, AIMessage):
            print(f"AI: {m.content}")
    print("\nDone.")


if __name__ == "__main__":
    run("Reverse the string 'Model Context Protocol'. Then explain what you did.")
