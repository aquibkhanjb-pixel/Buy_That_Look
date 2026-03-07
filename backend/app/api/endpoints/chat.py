"""AI Fashion Assistant chat endpoint — supports text + optional image input."""

import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Request, File, Form, UploadFile, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import logger
from app.schemas.chat import ChatResponse, WebSearchResult
from app.services.chat_service import chat_service
from app.services.llm_service import llm_service
from app.api.endpoints.search import convert_to_search_results

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
    # Optional image
    image: Optional[UploadFile] = File(default=None, description="Optional image for visual search"),
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

        # Run Gemini Vision to get a fashion description
        image_description = llm_service.describe_image(image_bytes)
        input_type = "hybrid" if last_msg.strip() else "image"
        logger.info(f"Chat image described: '{(image_description or '')[:60]}...'")

    # ── Invoke chat service ──
    logger.info(
        f"Chat [{cid[:8]}] — {len(parsed_messages)} messages, "
        f"type={input_type}, last='{last_msg[:50]}'"
    )

    result = chat_service.invoke(
        messages=parsed_messages,
        conversation_id=cid,
        input_type=input_type,
        image_description=image_description,
        user_preferences=prefs_dict,
        clarification_count=clarification_count,
    )

    # ── Convert products to SearchResult schema ──
    products = []
    if result.get("products_to_show"):
        products = convert_to_search_results(result["products_to_show"])

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
    )
