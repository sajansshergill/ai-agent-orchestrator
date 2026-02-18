import asyncio
import json

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

    add_message(db, conversation_id=conversation_id, role="user", content=payload.user_message)

    log_trace_step(db, conversation_id, "agent_start", "Starting agent run")

    log_tool_call(
        db,
        conversation_id=conversation_id,
        tool_name="mock_tool",
        input_payload={"query": payload.user_message},
        output_payload={"result": "ok"},
    )
    log_trace_step(db, conversation_id, "tool_call", "mock_tool executed successfully")

    assistant_text = run_simple_agent(payload.user_message)
    add_message(db, conversation_id=conversation_id, role="assistant", content=assistant_text)

    log_trace_step(db, conversation_id, "agent_end", "Completed agent run")

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
            log_trace_step(db, conversation_id, "agent_start", "Starting streamed agent run")
            yield sse("agent_start", {"conversation_id": conversation_id})

            log_tool_call(
                db,
                conversation_id=conversation_id,
                tool_name="mock_tool",
                input_payload={"query": payload.user_message},
                output_payload={"result": "ok"},
            )
            log_trace_step(db, conversation_id, "tool_call", "mock_tool executed successfully")
            yield sse("tool_call", {"tool_name": "mock_tool", "status": "ok"})

            assistant_text = run_simple_agent(payload.user_message)

            words = assistant_text.split(" ")
            built = []
            for i, w in enumerate(words):
                built.append(w)
                partial = " ".join(built)

                if i % 8 == 0:
                    log_trace_step(db, conversation_id, "stream_chunk", partial)

                yield sse("token", {"delta": w + " ", "partial": partial})
                await asyncio.sleep(0.02)

            add_message(db, conversation_id=conversation_id, role="assistant", content=assistant_text)

            log_trace_step(db, conversation_id, "agent_end", "Completed streamed agent run")
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
