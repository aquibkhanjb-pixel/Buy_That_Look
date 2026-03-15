"""Find This Look endpoint — discover products from any image URL or uploaded photo."""

import asyncio
import uuid
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, File, Form, UploadFile, HTTPException

from app.core.logging import logger
from app.schemas.chat import ChatResponse, WebSearchResult
from app.services.chat_service import chat_service
from app.services.llm_service import llm_service
from app.api.endpoints.chat import convert_to_search_results

router = APIRouter()

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
_INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com", "instagr.am"}


def _fetch_image_sync(url: str) -> bytes:
    """Synchronously fetch image bytes from a URL (runs in thread pool)."""
    import requests  # sync HTTP, always available

    headers = {"User-Agent": "Mozilla/5.0 (compatible; FashionFinder/1.0)"}
    r = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
    r.raise_for_status()

    content_type = r.headers.get("content-type", "")
    if not any(t in content_type for t in ["image/jpeg", "image/png", "image/webp", "image/"]):
        raise ValueError(
            f"URL does not point to a direct image (got: {content_type}). "
            "Try right-clicking the image and copying the image address, or upload a screenshot."
        )
    return r.content


@router.post("/", response_model=ChatResponse)
async def find_look(
    image_url: Optional[str] = Form(default=None, description="Direct image URL to analyse"),
    image: Optional[UploadFile] = File(default=None, description="Uploaded image file"),
):
    """
    Find This Look — given any image (URL or upload), find similar products online.

    Flow:
    1. Fetch/read image bytes
    2. Gemini Vision extracts clothing description
    3. LangGraph chat service runs image-search path (Serper)
    4. Returns products + web results
    """
    if not image_url and not image:
        raise HTTPException(status_code=422, detail="Provide either image_url or image file.")

    image_bytes: Optional[bytes] = None

    # ── Uploaded file ──────────────────────────────────────────────────────
    if image:
        if image.content_type not in _ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail="Invalid image type. Allowed: JPEG, PNG, WebP."
            )
        image_bytes = await image.read()
        if len(image_bytes) > _MAX_IMAGE_SIZE:
            raise HTTPException(status_code=400, detail="Image too large (max 10 MB).")

    # ── Image URL ──────────────────────────────────────────────────────────
    elif image_url:
        host = urlparse(image_url).netloc.lower()
        if host in _INSTAGRAM_HOSTS:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Instagram blocks direct image access. "
                    "Please take a screenshot of the post and upload it using the upload button."
                ),
            )
        try:
            loop = asyncio.get_event_loop()
            image_bytes = await loop.run_in_executor(None, _fetch_image_sync, image_url)
            logger.info(f"FindLook: fetched {len(image_bytes):,} bytes from {image_url[:80]}")
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Could not fetch image: {str(e)[:200]}"
            )

    # ── Gemini Vision: describe clothing ───────────────────────────────────
    image_description = llm_service.describe_image(image_bytes)
    if not image_description:
        raise HTTPException(
            status_code=422,
            detail="Could not identify clothing in this image. Please try a clearer photo showing the garment."
        )
    logger.info(f"FindLook: vision description = '{image_description[:80]}...'")

    # ── Chat service: image-search path (skips clarification) ─────────────
    result = chat_service.invoke(
        messages=[{"role": "user", "content": "Find me this clothing item"}],
        conversation_id=str(uuid.uuid4()),
        input_type="image",
        image_description=image_description,
        image_bytes=image_bytes,
        user_preferences={},
        clarification_count=0,
        from_trend=True,   # skips slot-filling clarification
    )

    # ── Convert results ────────────────────────────────────────────────────
    products = []
    if result.get("products_to_show"):
        products = convert_to_search_results(result["products_to_show"])

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
        conversation_id=str(uuid.uuid4()),
        search_performed=result.get("search_performed", False),
        web_search_performed=result.get("web_search_performed", False),
        user_preferences={},
        clarification_count=0,
        options=[],
    )
