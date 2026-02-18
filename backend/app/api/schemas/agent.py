from pydantic import BaseModel


class AgentRunRequest(BaseModel):
    user_message: str


class AgentRunResponse(BaseModel):
    conversation_id: str
    assistant_message: str
