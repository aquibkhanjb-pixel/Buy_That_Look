"""Chat history endpoints — premium users only."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_premium
from app.db.database import get_db
from app.db.models import ChatSession, ChatMessage

router = APIRouter()


@router.get("/")
def list_sessions(
    user: dict = Depends(require_premium),
    db: Session = Depends(get_db),
):
    """Return all chat sessions for the authenticated premium user, newest first."""
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user["sub"])
        .order_by(ChatSession.updated_at.desc())
        .limit(100)
        .all()
    )
    return {
        "sessions": [
            {
                "id":         s.id,
                "title":      s.title,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in sessions
        ]
    }


@router.get("/{session_id}")
def get_session_messages(
    session_id: str,
    user: dict = Depends(require_premium),
    db: Session = Depends(get_db),
):
    """Return all messages for a specific chat session (must belong to user)."""
    session_obj = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == user["sub"])
        .first()
    )
    if not session_obj:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return {
        "session_id":           session_id,
        "title":                session_obj.title,
        "user_preferences":     session_obj.user_preferences_json,   # raw JSON string
        "messages": [
            {
                "id":            m.id,
                "role":          m.role,
                "content":       m.content,
                "metadata_json": m.metadata_json,                    # raw JSON string or null
                "created_at":    m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.delete("/{session_id}")
def delete_session(
    session_id: str,
    user: dict = Depends(require_premium),
    db: Session = Depends(get_db),
):
    """Delete a chat session and all its messages (cascade)."""
    session_obj = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == user["sub"])
        .first()
    )
    if not session_obj:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(session_obj)
    db.commit()
    return {"status": "deleted"}
