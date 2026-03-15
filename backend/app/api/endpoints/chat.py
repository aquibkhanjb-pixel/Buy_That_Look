"""AI Fashion Assistant chat endpoint — supports text + optional image input."""

import json
import uuid
from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, Request, File, Form, UploadFile, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.logging import logger
from app.db.database import get_db
from app.db.models import UserUsage, ChatSession, ChatMessage
from app.schemas.chat import ChatResponse, WebSearchResult
from app.schemas.search import SearchResult
from app.services.chat_service import chat_service
from app.services.llm_service import llm_service

FREE_CHAT_LIMIT = 15

_optional_bearer = HTTPBearer(auto_error=False)


def _get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
) -> Optional[dict]:
    """Return decoded JWT payload if Bearer token provided, else None."""
    if credentials is None:
        return None
    try:
        return get_current_user(credentials)
    except Exception:
        return None


def convert_to_search_results(raw_results: List[dict]) -> List[SearchResult]:
    results = []
    for item in raw_results:
        try:
            results.append(SearchResult(
                id=str(item.get("id", "")),
                product_id=item.get("product_id", ""),
                title=item.get("title", "Unknown"),
                description=item.get("description"),
                brand=item.get("brand"),
                price=item.get("price"),
                original_price=item.get("original_price"),
                currency=item.get("currency", "USD"),
                category=item.get("category"),
                subcategory=item.get("subcategory"),
                color=item.get("color"),
                image_url=item.get("image_url", ""),
                product_url=item.get("product_url", ""),
                source_site=item.get("source_site", ""),
                similarity=item.get("similarity", 0.0),
                llm_score=item.get("llm_score"),
            ))
        except Exception as e:
            logger.warning(f"Failed to convert search result: {e}")
    return results

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat(
    request: Request,
    # Text fields (form data to support optional image upload)
    messages: str = Form(..., description="JSON array of {role, content} objects"),
    conversation_id: Optional[str] = Form(default=None),
    user_preferences: Optional[str] = Form(default=None, description="JSON dict of accumulated prefs"),
    clarification_count: int = Form(default=0),
    from_trend: bool = Form(default=False),
    outfit_product: Optional[str] = Form(default=None, description="JSON product dict to use as outfit reference"),
    # Optional image
    image: Optional[UploadFile] = File(default=None, description="Optional image for visual search"),
    # Optional auth (for tier-based limits)
    current_user: Optional[dict] = Depends(_get_optional_user),
    db: Session = Depends(get_db),
):
    """
    AI Fashion Assistant — conversational product discovery.

    Accepts:
    - A conversation history as JSON (messages field)
    - An optional image upload for visual search within chat
    - Accumulated user_preferences (sent back from previous response)

    Returns:
    - A natural language reply
    - Product cards (if search was performed)
    - Web search links (if local DB had no good matches)
    - Updated user_preferences (to send back on next turn)
    """
    cid = conversation_id or str(uuid.uuid4())

    # ── Daily chat limit for free-tier users ──
    if current_user and current_user.get("tier", "free") != "premium":
        user_id = current_user["sub"]
        today = date.today()
        usage = (
            db.query(UserUsage)
            .filter(UserUsage.user_id == user_id, UserUsage.date == today)
            .first()
        )
        if usage and usage.chat_count >= FREE_CHAT_LIMIT:
            raise HTTPException(
                status_code=403,
                detail=f"Daily limit reached. Free tier allows {FREE_CHAT_LIMIT} messages per day. Upgrade to Premium for unlimited chat.",
            )

    # ── Parse messages ──
    try:
        parsed_messages = json.loads(messages)
        if not isinstance(parsed_messages, list):
            raise ValueError("messages must be a JSON array")
    except Exception:
        raise HTTPException(status_code=422, detail="messages must be a valid JSON array")

    last_msg = next(
        (m.get("content", "") for m in reversed(parsed_messages) if m.get("role") == "user"),
        "",
    )

    # ── Parse accumulated preferences ──
    prefs_dict = {}
    if user_preferences:
        try:
            prefs_dict = json.loads(user_preferences)
        except Exception:
            prefs_dict = {}

    # ── Handle optional image ──
    image_description: Optional[str] = None
    image_bytes: Optional[bytes] = None
    input_type = "text"

    if image is not None:
        if image.content_type not in _ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid image type. Allowed: {', '.join(_ALLOWED_IMAGE_TYPES)}",
            )
        image_bytes = await image.read()
        if len(image_bytes) > _MAX_IMAGE_SIZE:
            raise HTTPException(status_code=400, detail="Image too large (max 10MB)")

        # Gemini Vision for feature extraction (garment type, style, occasion, gender)
        image_description = llm_service.describe_image(image_bytes)
        input_type = "hybrid" if last_msg.strip() else "image"
        logger.info(f"Chat image described: '{(image_description or '')[:60]}...'")

    # ── Invoke chat service ──
    logger.info(
        f"Chat [{cid[:8]}] — {len(parsed_messages)} messages, "
        f"type={input_type}, last='{last_msg[:50]}'"
    )

    # ── Parse outfit product (if "Complete the Look" was clicked) ──
    outfit_product_dict = None
    if outfit_product:
        try:
            outfit_product_dict = json.loads(outfit_product)
        except Exception:
            outfit_product_dict = None

    result = chat_service.invoke(
        messages=parsed_messages,
        conversation_id=cid,
        input_type=input_type,
        image_description=image_description,
        image_bytes=image_bytes,
        user_preferences=prefs_dict,
        clarification_count=clarification_count,
        from_trend=from_trend,
        outfit_product=outfit_product_dict,
    )

    # ── Convert products to SearchResult schema ──
    products = []
    if result.get("products_to_show"):
        products = convert_to_search_results(result["products_to_show"])

    # ── Increment daily chat count + persist history for premium ──
    if current_user:
        user_id = current_user["sub"]
        today = date.today()

        # Daily usage tracking (all authenticated users)
        usage = (
            db.query(UserUsage)
            .filter(UserUsage.user_id == user_id, UserUsage.date == today)
            .first()
        )
        if usage:
            usage.chat_count += 1
        else:
            db.add(UserUsage(user_id=user_id, date=today, chat_count=1))

        # Chat history persistence (premium users only)
        if current_user.get("tier") == "premium" and cid:
            from sqlalchemy import text as _text

            # Build metadata JSON for the assistant message (products + web links + options)
            meta = {}
            if result.get("products_to_show"):
                meta["products"] = result["products_to_show"]
            if result.get("web_results"):
                meta["web_results"] = result["web_results"]
            if result.get("clarification_options"):
                meta["options"] = result["clarification_options"]
            meta_json_str = json.dumps(meta) if meta else None

            # Latest user_preferences to restore context on resume
            prefs_json_str = json.dumps(result.get("user_preferences", {}))

            session_obj = db.query(ChatSession).filter(ChatSession.id == cid).first()
            if not session_obj:
                # First turn: create session row
                title = last_msg[:72].rstrip() + ("…" if len(last_msg) > 72 else "")
                session_obj = ChatSession(
                    id=cid,
                    user_id=user_id,
                    title=title or "New conversation",
                    user_preferences_json=prefs_json_str,
                )
                db.add(session_obj)
                db.flush()
                # Save the user message for this turn
                db.add(ChatMessage(session_id=cid, role="user", content=last_msg))
            else:
                # Subsequent turns: save user message + update preferences + touch updated_at
                db.add(ChatMessage(session_id=cid, role="user", content=last_msg))
                db.execute(
                    _text(
                        "UPDATE chat_sessions SET updated_at = NOW(), "
                        "user_preferences_json = :prefs WHERE id = :id"
                    ),
                    {"prefs": prefs_json_str, "id": cid},
                )

            # Save assistant reply with product/link metadata
            db.add(ChatMessage(
                session_id=cid,
                role="assistant",
                content=result["response"],
                metadata_json=meta_json_str,
            ))

        db.commit()

    # ── Convert web results to WebSearchResult schema ──
    web_results = []
    for wr in result.get("web_results", []):
        try:
            web_results.append(WebSearchResult(**wr))
        except Exception:
            continue

    return ChatResponse(
        message=result["response"],
        products=[p.model_dump() for p in products],
        web_results=web_results,
        conversation_id=cid,
        search_performed=result.get("search_performed", False),
        web_search_performed=result.get("web_search_performed", False),
        user_preferences=result.get("user_preferences", {}),
        clarification_count=result.get("clarification_count", 0),
        options=result.get("clarification_options", []),
        is_outfit_completion=result.get("is_outfit_completion", False),
    )
