"""
LLM Service — Gemini AI integration for vision.

Uses the new google-genai SDK (google-generativeai is deprecated).

Phase 2:
  - describe_image : generates a detailed text description of an uploaded image
                     using Gemini Vision (gemini-2.0-flash is natively multimodal)

All methods fall back gracefully if the API is unavailable.
"""

from typing import Optional

from loguru import logger

try:
    from langsmith import traceable
except ImportError:
    def traceable(**_kwargs):  # type: ignore[misc]
        def decorator(fn):
            return fn
        return decorator

try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-genai not installed — LLM features disabled")

_CHAT_MODEL = "gemini-2.5-flash"  # used for describe_image (richer vision understanding)


class LLMService:
    """Wrapper around the Google Gemini API (google-genai SDK)."""

    def __init__(self):
        self._client = None
        self._enabled = False

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def initialize(self, api_key: str) -> None:
        if not GEMINI_AVAILABLE:
            logger.warning("google-genai not installed — LLM service disabled")
            return
        if not api_key:
            logger.warning("GEMINI_API_KEY is empty — LLM service disabled")
            return
        try:
            self._client = genai.Client(api_key=api_key)
            self._enabled = True
            logger.info(f"LLM service initialised (Gemini / {_CHAT_MODEL})")
        except Exception as exc:
            logger.error(f"LLM service failed to initialise: {exc}")

    @property
    def is_enabled(self) -> bool:
        return self._enabled and self._client is not None

    # ------------------------------------------------------------------
    # Phase 2 — Image Description (Vision)
    # ------------------------------------------------------------------

    @traceable(name="describe_image", run_type="llm", tags=["gemini", "vision"])
    def describe_image(self, image_bytes: bytes) -> Optional[str]:
        """
        Generate a detailed fashion description of an uploaded image
        using Gemini Vision (gemini-2.0-flash is natively multimodal).

        Returns a description string, or None if Gemini is disabled/fails.

        Example output:
            "White formal shirt, slim fit, full sleeves, spread collar,
             button-down placket, solid colour, light fabric, men's wear"
        """
        if not self.is_enabled:
            return None

        try:
            import PIL.Image
            import io

            image = PIL.Image.open(io.BytesIO(image_bytes))

            prompt = (
                "Describe this fashion product image in detail for a visual search system.\n"
                "Include: garment type, colour, style, fit, fabric/texture if visible, "
                "occasion suitability, and gender if apparent.\n"
                "Be specific and concise (2-3 sentences). "
                "Focus only on the clothing/accessory, not the background or model."
            )

            response = self._client.models.generate_content(
                model=_CHAT_MODEL,   # 2.5-flash — better multimodal understanding
                contents=[image, prompt],
            )
            description = response.text.strip()
            logger.info(f"Image described: '{description[:80]}...'")
            return description

        except Exception as exc:
            logger.warning(f"Image description failed. Reason: {exc}")
            return None


# Singleton — imported everywhere
llm_service = LLMService()
