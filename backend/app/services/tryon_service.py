"""
Virtual Try-On Service — IDM-VTON via HuggingFace Gradio Spaces.

Fallback chain:
  1. yisol/IDM-VTON        — original IDM-VTON space
  2. Nymbo/Virtual-Try-On  — always-on featured space, no sleep

Note: CatVTON spaces (zhengchong, SaadAhmedSiddiqui, Shad0ws) are all
in RUNTIME_ERROR / NO_APP_FILE — abandoned by owners as of March 2026.

A HuggingFace token (HF_TOKEN in .env) is optional but recommended.
"""

import base64
import os
import tempfile
import time
from typing import Optional

import requests as _requests
from loguru import logger

_HF_TOKEN: str = ""

_DOWNLOAD_TIMEOUT = 15   # seconds for garment image download
_CLIENT_TIMEOUT   = 120  # seconds to wait for gradio space response

# ── IDM-VTON spaces (tried in order) ─────────────────────────────────────────
_IDM_SPACES = [
    "yisol/IDM-VTON",
    "Nymbo/Virtual-Try-On",   # always-on featured space, no sleep
]


class TryOnService:
    """Wrapper around HuggingFace virtual try-on Gradio Spaces."""

    def __init__(self):
        self._enabled = False
        self._last_model: str = ""

    def initialize(self, hf_token: str = "") -> None:
        global _HF_TOKEN
        try:
            import gradio_client  # noqa: F401
            _HF_TOKEN = hf_token
            self._enabled = True
            logger.info(
                f"Try-on service initialised "
                f"({'token set' if hf_token else 'anonymous'} / IDM-VTON primary)"
            )
        except ImportError:
            logger.warning("gradio_client not installed — virtual try-on disabled")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def last_model(self) -> str:
        return self._last_model

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def generate(
        self,
        person_bytes: bytes,
        garment_image_url: str,
        garment_description: str = "",
    ) -> Optional[str]:
        """
        Returns base64-encoded JPEG of the try-on result, or None on failure.
        """
        if not self.is_enabled:
            return None

        t0 = time.time()

        person_path  = self._save_bytes(person_bytes, ".jpg")
        garment_path = self._download_image(garment_image_url)

        if not person_path or not garment_path:
            _safe_unlink(person_path)
            _safe_unlink(garment_path)
            return None

        try:
            for space in _IDM_SPACES:
                result = self._call_idmvton(space, person_path, garment_path, garment_description)
                if result:
                    self._last_model = f"IDM-VTON via {space}"
                    logger.info(f"Try-on done via '{space}' in {int((time.time()-t0)*1000)} ms")
                    return result
                logger.info(f"Space '{space}' failed — trying next fallback")

            logger.warning("All try-on spaces failed")
            self._last_model = ""
            return None
        finally:
            _safe_unlink(person_path)
            _safe_unlink(garment_path)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _call_idmvton(
        self,
        space_id: str,
        person_path: str,
        garment_path: str,
        description: str,
    ) -> Optional[str]:
        try:
            from gradio_client import Client, handle_file

            logger.info(f"Connecting to HuggingFace space: {space_id}")
            client = Client(space_id, token=_HF_TOKEN or None)

            result = client.predict(
                dict={
                    "background": handle_file(person_path),
                    "layers": [],
                    "composite": None,
                },
                garm_img=handle_file(garment_path),
                garment_des=description or "fashion garment",
                is_checked=True,
                is_checked_crop=False,
                denoise_steps=30,
                seed=42,
                api_name="/tryon",
            )

            result_path = result[0] if isinstance(result, (list, tuple)) else result
            return _file_to_b64(result_path)

        except Exception as exc:
            exc_s = str(exc)
            if "sleep" in exc_s.lower() or "unavailable" in exc_s.lower():
                logger.warning(f"Space '{space_id}' sleeping/unavailable: {exc_s[:120]}")
            elif "queue" in exc_s.lower() or "timeout" in exc_s.lower():
                logger.warning(f"Space '{space_id}' queue/timeout: {exc_s[:120]}")
            else:
                logger.warning(f"Space '{space_id}' error: {exc_s[:120]}")
            return None

    @staticmethod
    def _save_bytes(data: bytes, suffix: str) -> Optional[str]:
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(data)
                return f.name
        except Exception as exc:
            logger.warning(f"Temp file save failed: {exc}")
            return None

    @staticmethod
    def _download_image(url: str) -> Optional[str]:
        # ── data: URL (base64-encoded inline image from frontend) ────────
        if url.startswith("data:"):
            try:
                header, b64data = url.split(",", 1)
                suf = ".png" if "png" in header else ".webp" if "webp" in header else ".jpg"
                image_bytes = base64.b64decode(b64data)
                with tempfile.NamedTemporaryFile(suffix=suf, delete=False) as f:
                    f.write(image_bytes)
                    return f.name
            except Exception as exc:
                logger.warning(f"data: URL decode failed: {exc}")
                return None

        # ── Regular HTTP/HTTPS URL ────────────────────────────────────────
        try:
            resp = _requests.get(
                url,
                timeout=_DOWNLOAD_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
            ct  = resp.headers.get("content-type", "")
            suf = ".png" if "png" in ct else ".jpg"
            with tempfile.NamedTemporaryFile(suffix=suf, delete=False) as f:
                f.write(resp.content)
                return f.name
        except Exception as exc:
            logger.warning(f"Garment image download failed ({url[:80]}): {exc}")
            return None


# ── Singleton ────────────────────────────────────────────────────────────────
tryon_service = TryOnService()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_unlink(path: Optional[str]) -> None:
    if path:
        try:
            os.unlink(path)
        except Exception:
            pass


def _file_to_b64(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception as exc:
        logger.warning(f"Result image read failed: {exc}")
        return None
