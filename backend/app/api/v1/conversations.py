from fastapi import APIRouter, Depends, HTTPException
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

router = APIRouter()


@router.post("/conversations", response_model=ConversationOut)
def create_conversation_route(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
):
    conv = create_conversation(db, title=payload.title)
    return conv


@router.post("/conversations/{conversation_id}/messages", response_model=MessageOut)
def add_message_route(
    conversation_id: str,
    payload: MessageCreate,
    db: Session = Depends(get_db),
):
    conv = get_conversation(db, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if payload.role not in {"user", "assistant", "system"}:
        raise HTTPException(status_code=400, detail="role must be user/assistant/system")

    msg = add_message(db, conversation_id, payload.role, payload.content)
    return msg


@router.get("/conversations/{conversation_id}", response_model=ConversationHistory)
def get_history_route(
    conversation_id: str,
    db: Session = Depends(get_db),
):
    conv = get_conversation(db, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs = list_messages(db, conversation_id)
    return {"conversation": conv, "messages": msgs}
