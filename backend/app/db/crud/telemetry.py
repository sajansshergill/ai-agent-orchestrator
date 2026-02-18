from sqlalchemy.orm import Session
from app.db.models import ToolCall, TraceStep


def log_trace_step(
    db: Session,
    conversation_id: str,
    step_type: str,
    content: str,
) -> TraceStep:
    step = TraceStep(
        conversation_id=conversation_id,
        step_type=step_type,
        content=content,
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    return step


def log_tool_call(
    db: Session,
    conversation_id: str,
    tool_name: str,
    input_payload: dict | None = None,
    output_payload: dict | None = None,
) -> ToolCall:
    call = ToolCall(
        conversation_id=conversation_id,
        tool_name=tool_name,
        input_payload=input_payload,
        output_payload=output_payload,
    )
    db.add(call)
    db.commit()
    db.refresh(call)
    return call
