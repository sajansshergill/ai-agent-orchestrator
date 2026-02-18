from __future__ import annotations

from typing import TypedDict, List, Dict, Any

from langgraph.graph import StateGraph

# Compatibility: END location differs across versions
try:
    from langgraph.graph import END  # newer versions
except Exception:
    END = "__end__"  # fallback used by older internals


class AgentState(TypedDict):
    conversation_id: str
    user_message: str
    plan: str
    tool_name: str
    tool_input: Dict[str, Any]
    tool_output: Dict[str, Any]
    final_answer: str
    events: List[Dict[str, Any]]


def _planner_node(state: AgentState) -> AgentState:
    plan = (
        "1) Identify the policy topic\n"
        "2) Retrieve relevant policy sections\n"
        "3) Summarize key rules in bullets\n"
        "4) Highlight edge cases (carryover, eligibility, approvals)\n"
    )
    state["plan"] = plan
    state["events"].append({"type": "planner", "plan": plan})
    return state


def _tool_node(state: AgentState) -> AgentState:
    tool_name = "mock_policy_kb_search"
    tool_input = {"query": state["user_message"]}
    tool_output = {
        "top_chunks": [
            "Employees accrue 20 days PTO per year, with sick time up to 40 hours/year where applicable.",
            "Baby bonding leave and maternity leave are available; specific durations vary by policy.",
            "Requests should be submitted in advance; approvals depend on manager coverage needs.",
        ]
    }
    state["tool_name"] = tool_name
    state["tool_input"] = tool_input
    state["tool_output"] = tool_output
    state["events"].append({"type": "tool", "tool_name": tool_name, "input": tool_input, "output": tool_output})
    return state


def _supervisor_node(state: AgentState) -> AgentState:
    chunks = state.get("tool_output", {}).get("top_chunks", [])
    summary = (
        "Here’s a structured summary of the leave policy (based on available policy excerpts):\n\n"
        "Key rules:\n"
        + "\n".join([f"- {c}" for c in chunks])
        + "\n\n"
        "If you tell me your location (state/country) and employee type, I can tailor the rules to your case."
    )
    state["final_answer"] = summary
    state["events"].append({"type": "supervisor", "final_answer": summary})
    return state


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("planner", _planner_node)
    g.add_node("tool", _tool_node)
    g.add_node("supervisor", _supervisor_node)

    g.set_entry_point("planner")
    g.add_edge("planner", "tool")
    g.add_edge("tool", "supervisor")
    g.add_edge("supervisor", END)

    return g.compile()


GRAPH = build_graph()


def run_langgraph_agent(conversation_id: str, user_message: str) -> AgentState:
    init_state: AgentState = {
        "conversation_id": conversation_id,
        "user_message": user_message,
        "plan": "",
        "tool_name": "",
        "tool_input": {},
        "tool_output": {},
        "final_answer": "",
        "events": [],
    }
    return GRAPH.invoke(init_state)


def stream_langgraph_agent(conversation_id: str, user_message: str):
    """
    Streams node-level events in a version-tolerant way.
    Some LangGraph versions stream dicts; some stream tuples.
    """
    init_state: AgentState = {
        "conversation_id": conversation_id,
        "user_message": user_message,
        "plan": "",
        "tool_name": "",
        "tool_input": {},
        "tool_output": {},
        "final_answer": "",
        "events": [],
    }

    stream_iter = GRAPH.stream(init_state)

    for item in stream_iter:
        # Newer: {"planner": state} dict
        if isinstance(item, dict):
            for node_name, node_state in item.items():
                yield ("node", {"node": node_name})

                if node_name == "planner":
                    yield ("planner", {"plan": node_state.get("plan", "")})

                elif node_name == "tool":
                    yield (
                        "tool",
                        {
                            "tool_name": node_state.get("tool_name", ""),
                            "input": node_state.get("tool_input", {}),
                            "output": node_state.get("tool_output", {}),
                        },
                    )

                elif node_name == "supervisor":
                    yield ("final", {"final_answer": node_state.get("final_answer", "")})

        # Older: (node_name, state) tuple
        elif isinstance(item, tuple) and len(item) == 2:
            node_name, node_state = item
            yield ("node", {"node": str(node_name)})
            node_state = node_state or {}

            if str(node_name) == "planner":
                yield ("planner", {"plan": node_state.get("plan", "")})

            elif str(node_name) == "tool":
                yield (
                    "tool",
                    {
                        "tool_name": node_state.get("tool_name", ""),
                        "input": node_state.get("tool_input", {}),
                        "output": node_state.get("tool_output", {}),
                    },
                )

            elif str(node_name) == "supervisor":
                yield ("final", {"final_answer": node_state.get("final_answer", "")})
