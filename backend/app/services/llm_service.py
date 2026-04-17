"""
LLM Service — Gemini AI integration for vision.

Uses the new google-genai SDK (google-generativeai is deprecated).

Phase 2:
  - describe_image : generates a detailed text description of an uploaded image
                     using Gemini Vision (gemini-2.0-flash is natively multimodal)

All methods fall back gracefully if the API is unavailable.
"""

import time
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

# ─────────────────────────────────────────────────────────────────────────────
# Shared Gemini circuit-breaker state
# Both chat_service and occasion_service import and use these helpers so that
# a single API error silences retries across the whole app.
# ─────────────────────────────────────────────────────────────────────────────

_circuit_until: float = 0.0    # epoch seconds — API calls blocked until this time
_perm_error: bool = False       # True when key is invalid / billing disabled (no retry)

# Error substrings that indicate a permanent configuration problem
_PERM_ERROR_SIGNALS = (
    "API_KEY_INVALID",
    "INVALID_ARGUMENT",
    "PERMISSION_DENIED",
    "UNAUTHENTICATED",
    "billing",
    "401",
    "403",
)


def report_gemini_error(exc_str: str) -> None:
    """
    Call this whenever a Gemini API call raises an exception.
    Updates the shared circuit-breaker so all subsequent calls skip the API
    instead of hammering it with requests that will also fail.
    """
    global _circuit_until, _perm_error
    s = exc_str.lower()

    if any(sig.lower() in s for sig in _PERM_ERROR_SIGNALS):
        # Permanent — bad key or billing issue.  Block for 24 h (until server restart).
        _perm_error = True
        _circuit_until = time.time() + 86400
        logger.error(
            "Gemini API: permanent error (invalid key / permission denied). "
            "AI features disabled until server restart."
        )
    elif "resource_exhausted" in s or "429" in s:
        # Quota exhausted — back off for 1 hour
        _circuit_until = time.time() + 3600
        logger.warning("Gemini quota exhausted — circuit breaker active for 1 h")
    elif "unavailable" in s or "503" in s:
        # Transient service outage — back off 30 s
        _circuit_until = max(_circuit_until, time.time() + 30)
        logger.warning("Gemini service unavailable — circuit breaker active for 30 s")
    else:
        # Unknown error — short back-off
        _circuit_until = max(_circuit_until, time.time() + 10)
        logger.warning(f"Gemini call failed: {exc_str}")


def is_gemini_circuit_open() -> bool:
    """Return True when the circuit breaker is active (API calls should be skipped)."""
    return time.time() < _circuit_until


def gemini_unavailable_message() -> str:
    """
    Return a polished, recruiter-friendly message shown in the chat UI when
    the Gemini API is unavailable.
    """
    if _perm_error:
        return (
            "Our AI assistant is currently offline due to an API configuration issue. "
            "We're working on restoring it soon!\n\n"
            "In the meantime, you can still:\n"
            "• Search for products using the search bar\n"
            "• Browse trending styles on the home page\n"
            "• Use the Occasion Planner for curated outfit ideas"
        )
    return (
        "Our AI assistant is temporarily unavailable — likely due to high demand or "
        "an API quota limit being reached.\n\n"
        "In the meantime, you can still:\n"
        "• Search for products using the search bar\n"
        "• Browse trending styles on the home page\n"
        "• Use the Occasion Planner for curated outfit ideas\n\n"
        "Please try again in a few minutes!"
    )


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
        if is_gemini_circuit_open():
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
            report_gemini_error(str(exc))
            return None


# Singleton — imported everywhere
llm_service = LLMService()
