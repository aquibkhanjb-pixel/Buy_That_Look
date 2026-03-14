"""Virtual Try-On endpoint — person photo + garment image → composite result."""

import time
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.logging import logger
from app.schemas.tryon import TryOnResponse
from app.services.tryon_service import tryon_service

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/", response_model=TryOnResponse)
@limiter.limit("10/minute")
async def virtual_tryon(
    request: Request,
    person_image: UploadFile = File(..., description="Full-body photo of the user"),
    garment_image_url: str = Form(..., description="URL of the product/garment image"),
    garment_description: Optional[str] = Form(default="", description="Short description of the garment"),
):
    """
    Virtual Try-On — overlay a recommended garment onto the user's full-body photo.

    Accepts:
    - person_image       : JPEG/PNG/WebP full-body photo
    - garment_image_url  : URL of the product image (from product card or web result)
    - garment_description: optional text description for better accuracy

    Returns:
    - result_image       : base64-encoded JPEG of the try-on composite
    """
    if not tryon_service.is_enabled:
        raise HTTPException(
            status_code=503,
            detail="Virtual try-on service is not available. Please install gradio_client and restart.",
        )

    # ── Validate person image ──────────────────────────────────────────
    if person_image.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid image type. Allowed: {', '.join(_ALLOWED_IMAGE_TYPES)}",
        )
    person_bytes = await person_image.read()
    if len(person_bytes) > _MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Image too large (max 10 MB)")

    if not garment_image_url.strip():
        raise HTTPException(status_code=400, detail="garment_image_url is required")

    # ── Run try-on ────────────────────────────────────────────────────
    t0 = time.time()
    logger.info(
        f"Try-on request | garment='{(garment_description or garment_image_url)[:60]}'"
    )

    result_b64 = tryon_service.generate(
        person_bytes=person_bytes,
        garment_image_url=garment_image_url,
        garment_description=garment_description or "",
    )

    if not result_b64:
        raise HTTPException(
            status_code=502,
            detail="Try-on generation failed. The HuggingFace space may be unavailable or queued. Please try again.",
        )

    elapsed = int((time.time() - t0) * 1000)
    logger.info(f"Try-on complete in {elapsed} ms")

    return TryOnResponse(
        result_image=result_b64,
        model_used="IDM-VTON (HuggingFace)",
        latency_ms=elapsed,
    )
