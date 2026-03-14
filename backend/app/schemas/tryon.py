"""Schemas for the Virtual Try-On endpoint."""

from pydantic import BaseModel


class TryOnResponse(BaseModel):
    """Response from the virtual try-on endpoint."""
    result_image: str        # base64-encoded JPEG of the try-on result
    model_used: str          # which HuggingFace space was used
    latency_ms: int
