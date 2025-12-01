"""
Railway-safe Gemini LLM wrapper.

Features:
- Lazy SDK import/configuration (no heavy work at import time).
- Safe fallback when SDK or credentials are unavailable.
- Async `generate()` (ADK-friendly) and sync `__call__` for legacy codepaths.
- Robust exception handling (logs errors, doesn't raise from init).
"""

import os
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Globals populated by lazy loader
_genai = None            # the imported google.generativeai module (if available)
_genai_ready = False     # whether genai is initialized & configured
_genai_error = None      # store last error for diagnostics


def _ensure_genai():
    """Lazy import/configure google.generativeai (safe, idempotent)."""
    global _genai, _genai_ready, _genai_error

    if _genai_ready:
        return True

    if not GEMINI_API_KEY:
        _genai_ready = False
        _genai_error = "GEMINI_API_KEY not set"
        return False

    # Try import & configure
    try:
        import importlib

        genai = importlib.import_module("google.generativeai")
        # Some versions use genai.configure(api_key=...), others may require different setup.
        try:
            genai.configure(api_key=GEMINI_API_KEY)
        except Exception:
            # Older/newer adaptions — ignore if configure isn't available.
            pass

        # Assign into global
        _genai = genai
        _genai_ready = True
        _genai_error = None
        logger.info("Gemini SDK (google.generativeai) loaded and configured.")
        return True
    except Exception as e:
        _genai_ready = False
        _genai_error = str(e)
        logger.warning("Failed to load/configure google.generativeai: %s", e)
        return False


class LLM:
    """Lightweight LLM wrapper with async generate() and sync __call__.

    Does not perform heavy work at construction time. Calls attempt to use
    remote Gemini if configured; otherwise return deterministic fallback text.
    """

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        # instance-level enabled flag; true only if genai ready on first call
        self._remote_enabled = None  # None = unknown, True/False after first attempt

    def __call__(self, prompt: str, max_tokens: int = 512, temperature: float = 0.0, **kwargs) -> str:
        """Synchronous call (legacy codepaths)."""
        # Try remote on first usage if available
        if self._remote_enabled is None:
            self._remote_enabled = _ensure_genai()

        if not self._remote_enabled:
            return self._fallback(prompt)

        try:
            return self._sync_generate(prompt, max_tokens=max_tokens, temperature=temperature, **kwargs)
        except Exception as e:
            logger.warning("LLM sync call failed, falling back: %s", e)
            # disable remote for this instance on fatal SDK errors
            self._remote_enabled = False
            return self._fallback(prompt)

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.0, **kwargs) -> str:
        """Async generation API (ADK-friendly). Uses a thread for blocking SDK calls."""
        # Ensure genai on first use
        if self._remote_enabled is None:
            self._remote_enabled = _ensure_genai()

        if not self._remote_enabled:
            return self._fallback(prompt)

        try:
            return await asyncio.to_thread(self._sync_generate, prompt, max_tokens, temperature, **kwargs)
        except Exception as e:
            logger.warning("LLM async generate failed, falling back: %s", e)
            self._remote_enabled = False
            return self._fallback(prompt)

    def _sync_generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.0, **kwargs) -> str:
        """Blocking call into the underlying SDK. Must be called from thread / sync context."""
        global _genai, _genai_ready, _genai_error

        if not _ensure_genai():
            raise RuntimeError(f"GenAI not available: {_genai_error}")

        # Use different calling patterns depending on SDK offering
        try:
            # Pattern A: genai.GenerativeModel(...)
            if hasattr(_genai, "GenerativeModel"):
                model = _genai.GenerativeModel(self.model)
                # Some SDKs provide `model.generate_content(prompt=...)`
                if hasattr(model, "generate_content"):
                    resp = model.generate_content(prompt)
                    # resp may have .text or other attributes depending on SDK
                    if hasattr(resp, "text") and resp.text:
                        return resp.text.strip()
                    return str(resp)
                # fallback: try model.generate
                if hasattr(model, "generate"):
                    resp = model.generate(prompt=prompt)
                    if hasattr(resp, "text"):
                        return resp.text.strip()
                    return str(resp)

            # Pattern B: genai.generate_text(...)
            if hasattr(_genai, "generate_text"):
                # different SDK versions return different shapes
                resp = _genai.generate_text(model=self.model, prompt=prompt, max_output_tokens=max_tokens)
                # resp might have .candidates or .text
                if hasattr(resp, "text") and resp.text:
                    return resp.text.strip()
                if hasattr(resp, "candidates") and resp.candidates:
                    cand = resp.candidates[0]
                    # candidate may have `.content` or `.output_text`
                    if hasattr(cand, "content"):
                        return getattr(cand, "content").strip()
                    if hasattr(cand, "output_text"):
                        return getattr(cand, "output_text").strip()
                # last resort:
                return str(resp)

            # Pattern C: older genai.chat or other API
            if hasattr(_genai, "chat"):
                # best-effort call
                resp = _genai.chat.create(model=self.model, prompt=prompt)
                if hasattr(resp, "candidates") and resp.candidates:
                    return getattr(resp.candidates[0], "content", str(resp)).strip()
                return str(resp)

            # If none of the above patterns matched, raise to fallback
            raise RuntimeError("No supported genai call pattern found")
        except Exception as e:
            # Log full exception and re-raise to allow caller to handle fallback
            logger.exception("Remote Gemini call failed: %s", e)
            raise

    def _fallback(self, prompt: str) -> str:
        """Deterministic, small local fallback for offline/test runs."""
        p = (prompt or "").lower()

        # Task extraction heuristic
        if "extract tasks" in p or ("task" in p and "json" in p):
            return '[ {"title": "Sample task", "due": "2025-12-25T09:00:00", "priority": "Medium"} ]'

        # Scheduling/planner heuristic
        if "schedule" in p or "plan" in p:
            return '{"events": [ {"title": "Morning standup", "start_time": "2025-12-25T09:00:00", "duration_mins": 30, "notes": ""}, {"title": "Work on tasks", "start_time": "2025-12-25T09:30:00", "duration_mins": 180, "notes": ""} ], "assumptions": ["Tasks prioritized by deadline"] }'

        # Weekly summary/report heuristic
        if "weekly" in p or "summary" in p or "report" in p:
            return '{"summary": "Productive week with steady progress", "completed_count": 3, "pending_count": 2, "top_actions": ["Continue current task", "Review next priorities"] }'

        # Generic ack
        return '{"status": "acknowledged"}'


# Export a convenient default instance (safe to create)
DEFAULT_LLM = LLM()