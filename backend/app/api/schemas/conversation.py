from datetime import datetime
from pydantic import BaseModel

class ConversationCreate(BaseModel):
    title: str | None = None
    
class ConversationOut(BaseModel):
    id: str
    title: str | None
    created_at: datetime
    
    class Config:
        from_attributes = True