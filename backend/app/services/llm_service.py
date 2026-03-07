"""
LLM Service — Gemini AI integration for query expansion, re-ranking and vision.

Uses the new google-genai SDK (google-generativeai is deprecated).

Phase 1:
  - expand_query   : rewrites vague queries into rich fashion descriptions
  - rerank_results : scores CLIP candidates 0-10 and sorts by relevance

Phase 2:
  - describe_image : generates a detailed text description of an uploaded image
                     using Gemini Vision (gemini-2.0-flash is natively multimodal)

All methods fall back gracefully if the API is unavailable.
"""

import json
import re
from typing import Optional

from loguru import logger

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-genai not installed — LLM features disabled")

_MODEL = "gemini-flash-lite-latest"


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
            logger.info(f"LLM service initialised (Gemini / {_MODEL})")
        except Exception as exc:
            logger.error(f"LLM service failed to initialise: {exc}")

    @property
    def is_enabled(self) -> bool:
        return self._enabled and self._client is not None

    # ------------------------------------------------------------------
    # Phase 1A — Query Expansion
    # ------------------------------------------------------------------

    def expand_query(self, query: str) -> str:
        """
        Rewrite a vague user query into a detailed fashion product description.

        Example:
            "something for a beach party"
            → "flowy casual sundress, light fabric, bright or pastel colours,
               summer style, suitable for outdoor beach occasion"

        Returns original query unchanged if Gemini is disabled or fails.
        """
        if not self.is_enabled:
            return query

        try:
            prompt = (
                f'A user is searching for fashion products with this query: "{query}"\n\n'
                "Rewrite it as a specific, detailed fashion product description "
                "optimised for visual similarity search.\n"
                "Include relevant attributes: garment type, colour, style, occasion, "
                "fit, fabric — only what can be reasonably inferred.\n"
                "Keep it to 1–2 sentences. Return ONLY the expanded query, no explanation."
            )

            response = self._client.models.generate_content(
                model=_MODEL,
                contents=prompt,
            )
            expanded = response.text.strip()

            if expanded and expanded != query:
                logger.info(f"Query expanded | '{query}' → '{expanded}'")
                return expanded
            return query

        except Exception as exc:
            logger.warning(f"Query expansion failed — using original. Reason: {exc}")
            return query

    # ------------------------------------------------------------------
    # Phase 1B — Result Re-ranking
    # ------------------------------------------------------------------

    def rerank_results(self, query: str, results: list) -> list:
        """
        Score each CLIP result for relevance against the user's query.

        Scoring (0–10):
            ≥ 6  → top result        (shown in "Top Results" section)
            3–5  → possible match    (shown in "Other Possible Matches")
            < 3  → hidden entirely

        Each dict in `results` gets: "llm_score" (float | None).
        List is sorted by llm_score descending.
        Falls back to original CLIP order with llm_score=None if Gemini fails.
        """
        if not self.is_enabled or not results:
            for r in results:
                r["llm_score"] = None
            return results

        try:
            lines = [
                f"ID:{r.get('id', '')} | {r.get('title', 'Unknown')} | {r.get('category', '')}"
                for r in results
            ]
            products_text = "\n".join(lines)

            prompt = (
                f'A user searched for: "{query}"\n\n'
                "Rate how relevant each product is to this query.\n"
                "Scale 0–10: 10=perfect match, 6=relevant, 3=loosely related, 0=unrelated.\n"
                "Be strict — only give high scores to genuinely relevant products.\n\n"
                f"Products:\n{products_text}\n\n"
                "Return ONLY a JSON array, no markdown, no explanation:\n"
                '[{"id": "product_id_here", "score": 8}, ...]'
            )

            response = self._client.models.generate_content(
                model=_MODEL,
                contents=prompt,
            )
            response_text = response.text.strip()

            json_match = re.search(r"\[.*\]", response_text, re.DOTALL)
            if not json_match:
                raise ValueError(f"No JSON array in response: {response_text[:200]}")

            scores_data = json.loads(json_match.group())
            score_map: dict[str, float] = {
                str(item["id"]): float(item["score"]) for item in scores_data
            }

            for r in results:
                pid = str(r.get("id", ""))
                r["llm_score"] = score_map.get(pid, 5.0)

            results.sort(key=lambda x: x.get("llm_score") or 0, reverse=True)

            top_scores = [round(r["llm_score"], 1) for r in results[:5]]
            logger.info(
                f"Re-ranked {len(results)} results for '{query[:40]}' | "
                f"top-5 scores: {top_scores}"
            )
            return results

        except Exception as exc:
            logger.warning(f"Re-ranking failed — returning CLIP order. Reason: {exc}")
            for r in results:
                r["llm_score"] = None
            return results

    # ------------------------------------------------------------------
    # Phase 2 — Image Description (Vision)
    # ------------------------------------------------------------------

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
                model=_MODEL,
                contents=[image, prompt],
            )
            description = response.text.strip()
            logger.info(f"Image described: '{description[:80]}...'")
            return description

        except Exception as exc:
            logger.warning(f"Image description failed — falling back to CLIP only. Reason: {exc}")
            return None


# Singleton — imported everywhere
llm_service = LLMService()
