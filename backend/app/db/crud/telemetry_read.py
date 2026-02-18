from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TraceStep, ToolCall


def list_trace_steps(db: Session, conversation_id: str) -> list[TraceStep]:
    stmt = (
        select(TraceStep)
        .where(TraceStep.conversation_id == conversation_id)
        .order_by(TraceStep.created_at.asc())
    )
    return list(db.scalars(stmt).all())


def list_tool_calls(db: Session, conversation_id: str) -> list[ToolCall]:
    stmt = (
        select(ToolCall)
        .where(ToolCall.conversation_id == conversation_id)
        .order_by(ToolCall.created_at.asc())
    )
    return list(db.scalars(stmt).all())
