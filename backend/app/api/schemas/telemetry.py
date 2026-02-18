from datetime import datetime
from pydantic import BaseModel, ConfigDict


class TraceStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    step_type: str
    content: str
    created_at: datetime


class ToolCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    tool_name: str
    input_payload: dict | None
    output_payload: dict | None
    created_at: datetime


class TelemetryOut(BaseModel):
    trace_steps: list[TraceStepOut]
    tool_calls: list[ToolCallOut]
