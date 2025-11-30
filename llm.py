"""Gemini LLM wrapper with async `generate()` for ADK compatibility.

This module keeps a synchronous callable for backward compatibility but
adds an async `generate()` method so ADK agents can `await llm.generate(...)`.
"""

import os
import logging
import asyncio
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

try:
    if GEMINI_API_KEY:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=GEMINI_API_KEY)
        _GENAI_AVAILABLE = True
        logger.info("Gemini API initialized successfully.")
    else:
        _GENAI_AVAILABLE = False
        logger.info("Gemini API key not found. Using fallback mode.")
except Exception as e:
    logger.warning(f"Gemini initialization failed: {e}")
    _GENAI_AVAILABLE = False


class LLM:
    """LLM wrapper supporting both sync call and async generate().

    - `llm = LLM()` creates an instance.
    - `await llm.generate(prompt, ...)` is the preferred async API.
    - `llm(prompt, ...)` remains supported for existing synchronous code.
    """

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self.enabled = _GENAI_AVAILABLE

    def __call__(self, prompt: str, max_tokens: int = 512, temperature: float = 0.0, **kwargs) -> str:
        """Synchronous call (backward compatible)."""
        if not self.enabled:
            return self._fallback(prompt)

        try:
            model = genai.GenerativeModel(self.model)
            response = model.generate_content(prompt)
            if hasattr(response, "text") and response.text:
                return response.text.strip()
            return str(response)
        except Exception as e:
            msg = str(e).lower()
            logger.warning(f"LLM sync call failed: {e}")
            # If the error indicates the model or method is not available,
            # disable remote Gemini for this instance and fall back.
            if "404" in msg or "not found" in msg or "not supported" in msg:
                logger.info("Disabling remote Gemini for this LLM instance (fallback mode).")
                self.enabled = False
            return self._fallback(prompt)

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.0, **kwargs) -> str:
        """Async generation API compatible with ADK agents.

        Uses thread execution for blocking SDK calls so the async loop isn't blocked.
        """
        if not self.enabled:
            return self._fallback(prompt)

        try:
            # run the blocking SDK call in a thread
            return await asyncio.to_thread(self._sync_generate, prompt, max_tokens, temperature, **kwargs)
        except Exception as e:
            msg = str(e).lower()
            logger.warning(f"LLM async generate failed: {e}")
            if "404" in msg or "not found" in msg or "not supported" in msg:
                logger.info("Disabling remote Gemini for this LLM instance (fallback mode).")
                self.enabled = False
            return self._fallback(prompt)

    def _sync_generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.0, **kwargs) -> str:
        model = genai.GenerativeModel(self.model)
        response = model.generate_content(prompt)
        if hasattr(response, "text") and response.text:
            return response.text.strip()
        return str(response)

    def _fallback(self, prompt: str) -> str:
        p = prompt.lower()

        if "extract tasks" in p or ("task" in p and "json" in p):
            return "[ {\"title\": \"Sample task\", \"due\": \"2025-12-25T09:00:00\", \"priority\": \"Medium\"} ]"

        if "schedule" in p or "plan" in p:
            return "{\"events\": [ {\"title\": \"Morning standup\", \"start_time\": \"2025-12-25T09:00:00\", \"duration_mins\": 30, \"notes\": \"\"}, {\"title\": \"Work on tasks\", \"start_time\": \"2025-12-25T09:30:00\", \"duration_mins\": 180, \"notes\": \"\"} ], \"assumptions\": [\"Tasks prioritized by deadline\"] }"

        if "weekly" in p or "summary" in p or "report" in p:
            return "{\"summary\": \"Productive week with steady progress\", \"completed_count\": 3, \"pending_count\": 2, \"top_actions\": [\"Continue current task\", \"Review next priorities\"] }"

        return '{"status": "acknowledged"}'


# Export a convenient default instance for synchronous codepaths
DEFAULT_LLM = LLM()

