import os
import json
from typing import List, TypedDict, Annotated
from dotenv import load_dotenv

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# Prefer the newer provider-specific package (avoids deprecation + NotImplemented errors)
try:
    from langchain_openai import ChatOpenAI  # type: ignore
except ImportError:  # Fallback (older style - will warn)
    from langchain.chat_models import ChatOpenAI  # type: ignore

# 1. Load env vars (.env should contain OPENAI_API_KEY; weather key removed)
load_dotenv()

# 2. Reverse string tool
@tool
def reverse_text(text: str) -> str:
    """Return the reversed form of the input text."""
    if text is None:
        return "Error: 'text' argument is required."
    return text[::-1]

# 3. State definition
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], "Conversation messages"]

# 4. LLM with tool binding (ReAct)
if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("Missing OPENAI_API_KEY in environment. Set it in your .env file.")

base_model = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    temperature=0,
    verbose=False
)

try:
    model = base_model.bind_tools([reverse_text])
except NotImplementedError:
    # Some legacy versions may not implement bind_tools; proceed without tool binding
    model = base_model

# 5. Graph nodes
def llm_node(state: AgentState):
    msgs = state["messages"]
    response = model.invoke(msgs)
    return {"messages": msgs + [response]}

def tool_node(state: AgentState):
    msgs: List[BaseMessage] = state["messages"]
    last = msgs[-1]
    new_msgs: List[BaseMessage] = []
    if isinstance(last, AIMessage) and getattr(last, 'tool_calls', None):
        for tc in last.tool_calls:
            if tc["name"] == "reverse_text":
                arg_text = tc["args"].get("text") or tc["args"].get("input") or tc["args"].get("value")
                if arg_text is None:
                    result = "Tool usage error: missing 'text' argument."
                else:
                    result = reverse_text.invoke({"text": arg_text})
                new_msgs.append(ToolMessage(name=tc["name"], content=result, tool_call_id=tc["id"]))
    return {"messages": msgs + new_msgs}

def should_continue(state: AgentState):
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and getattr(last, 'tool_calls', None):
        return "tools"
    return END

# 6. Build graph
graph = StateGraph(AgentState)
graph.add_node("llm", llm_node)
graph.add_node("tools", tool_node)
graph.set_entry_point("llm")
graph.add_conditional_edges("llm", should_continue)
graph.add_edge("tools", "llm")

memory = MemorySaver()
app = graph.compile(checkpointer=memory)

# 7. Simple run helper
def run(query: str):
    print(f"User: {query}")
    config = {"configurable": {"thread_id": "demo"}}
    state = {"messages": [HumanMessage(content=query)]}
    for update in app.stream(state, config=config):
        for node_name, node_state in update.items():
            last = node_state["messages"][-1]
            if isinstance(last, AIMessage) and getattr(last, 'tool_calls', None):
                print(f"[{node_name}] Model requested tool(s): " +
                      ", ".join(f"{tc['name']}({json.dumps(tc['args'])})" for tc in last.tool_calls))
            elif isinstance(last, ToolMessage):
                print(f"[tool:{last.name}] {last.content}")
            elif isinstance(last, AIMessage):
                print(f"AI: {last.content}")
    final = app.get_state(config).values["messages"][-1]
    if isinstance(final, AIMessage):
        print("\nFinal Answer:\n" + final.content)

if __name__ == "__main__":
    # Example prompt – model should decide to reverse the string
    run("Reverse the string 'Model Context Protocol'. Then explain what you did.")
