import asyncio
import json

from app.agents.langgraph_agent import run_langgraph_agent, stream_langgraph_agent
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.crud.conversations import (
    create_conversation,
    get_conversation,
    add_message,
    list_messages,
)
from app.api.schemas.conversation import ConversationCreate, ConversationOut
from app.api.schemas.message import MessageCreate, MessageOut
from app.api.schemas.history import ConversationHistory

from app.api.schemas.agent import AgentRunRequest, AgentRunResponse
from app.db.crud.telemetry import log_trace_step, log_tool_call
from app.agents.simple_agent import run_simple_agent

from app.api.schemas.telemetry import TelemetryOut
from app.db.crud.telemetry_read import list_trace_steps, list_tool_calls

router = APIRouter()


@router.post("/conversations", response_model=ConversationOut)
def create_conversation_route(payload: ConversationCreate, db: Session = Depends(get_db)):
    return create_conversation(db, title=payload.title)


@router.post("/conversations/{conversation_id}/messages", response_model=MessageOut)
def add_message_route(conversation_id: str, payload: MessageCreate, db: Session = Depends(get_db)):
    conv = get_conversation(db, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if payload.role not in {"user", "assistant", "system"}:
        raise HTTPException(status_code=400, detail="role must be user/assistant/system")

    return add_message(db, conversation_id=conversation_id, role=payload.role, content=payload.content)


@router.get("/conversations/{conversation_id}", response_model=ConversationHistory)
def get_history_route(conversation_id: str, db: Session = Depends(get_db)):
    conv = get_conversation(db, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs = list_messages(db, conversation_id)
    return {"conversation": conv, "messages": msgs}

@router.post("/conversations/{conversation_id}/run", response_model=AgentRunResponse)
def run_agent_route(conversation_id: str, payload: AgentRunRequest, db: Session = Depends(get_db)):
    conv = get_conversation(db, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Persist user message
    add_message(db, conversation_id=conversation_id, role="user", content=payload.user_message)
    log_trace_step(db, conversation_id, "agent_start", "Starting LangGraph agent run")

    # Run graph
    result_state = run_langgraph_agent(conversation_id, payload.user_message)

    # Log node outputs to trace_steps + tool_calls
    if result_state.get("plan"):
        log_trace_step(db, conversation_id, "planner", result_state["plan"])

    if result_state.get("tool_name"):
        log_tool_call(
            db,
            conversation_id=conversation_id,
            tool_name=result_state["tool_name"],
            input_payload=result_state.get("tool_input", {}),
            output_payload=result_state.get("tool_output", {}),
        )
        log_trace_step(db, conversation_id, "tool_call", f"Executed {result_state['tool_name']}")

    assistant_text = result_state.get("final_answer", "")
    add_message(db, conversation_id=conversation_id, role="assistant", content=assistant_text)
    log_trace_step(db, conversation_id, "agent_end", "Completed LangGraph agent run")

    return AgentRunResponse(conversation_id=conversation_id, assistant_message=assistant_text)
@router.post("/conversations/{conversation_id}/run/stream")
def run_agent_stream_route(conversation_id: str, payload: AgentRunRequest, db: Session = Depends(get_db)):
    conv = get_conversation(db, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    add_message(db, conversation_id=conversation_id, role="user", content=payload.user_message)

    async def event_generator():
        def sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        try:
            log_trace_step(db, conversation_id, "agent_start", "Starting LangGraph streamed run")
            yield sse("agent_start", {"conversation_id": conversation_id})

            final_answer = ""

            # Stream LangGraph node events
            for event_name, payload_dict in stream_langgraph_agent(conversation_id, payload.user_message):
                if event_name == "node":
                    log_trace_step(db, conversation_id, "node", f"Entered node: {payload_dict['node']}")
                    yield sse("node", payload_dict)

                elif event_name == "planner":
                    log_trace_step(db, conversation_id, "planner", payload_dict.get("plan", ""))
                    yield sse("planner", payload_dict)

                elif event_name == "tool":
                    tool_name = payload_dict.get("tool_name", "")
                    log_tool_call(
                        db,
                        conversation_id=conversation_id,
                        tool_name=tool_name,
                        input_payload=payload_dict.get("input", {}),
                        output_payload=payload_dict.get("output", {}),
                    )
                    log_trace_step(db, conversation_id, "tool_call", f"Executed {tool_name}")
                    yield sse("tool_call", {"tool_name": tool_name, "status": "ok"})

                elif event_name == "final":
                    final_answer = payload_dict.get("final_answer", "")
                    # Stream the final answer word-by-word (works nicely with your UI)
                    words = final_answer.split(" ")
                    built = []
                    for i, w in enumerate(words):
                        built.append(w)
                        partial = " ".join(built)
                        if i % 10 == 0:
                            log_trace_step(db, conversation_id, "stream_chunk", partial)
                        yield sse("token", {"delta": w + " ", "partial": partial})
                        await asyncio.sleep(0.02)

            # Persist assistant message at end
            add_message(db, conversation_id=conversation_id, role="assistant", content=final_answer)

            log_trace_step(db, conversation_id, "agent_end", "Completed LangGraph streamed run")
            yield sse("agent_end", {"conversation_id": conversation_id, "status": "done"})

        except Exception as e:
            log_trace_step(db, conversation_id, "agent_error", str(e))
            yield sse("error", {"message": str(e)})

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)

@router.get("/conversations/{conversation_id}/telemetry", response_model=TelemetryOut)
def get_telemetry_route(conversation_id: str, db: Session = Depends(get_db)):
    conv = get_conversation(db, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {
        "trace_steps": list_trace_steps(db, conversation_id),
        "tool_calls": list_tool_calls(db, conversation_id),
    }
