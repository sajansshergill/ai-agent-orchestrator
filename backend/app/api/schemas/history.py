from pydantic import BaseModel
from app.api.schemas.conversation import ConversationOut
from app.api.schemas.message import MessageOut

class ConversationHistory(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]