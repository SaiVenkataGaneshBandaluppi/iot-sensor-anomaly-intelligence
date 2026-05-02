import contextvars
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_groq_client = None
_client_initialized = False
_request_api_key: contextvars.ContextVar[str] = contextvars.ContextVar("_request_api_key", default="")


def get_groq_client() -> Any | None:
    global _groq_client, _client_initialized
    if _client_initialized:
        return _groq_client
    _client_initialized = True
    try:
        from app.config import settings

        if not settings.GROQ_API_KEY:
            logger.info("GROQ_API_KEY not set; Groq client disabled")
            return None
        import groq

        _groq_client = groq.Groq(api_key=settings.GROQ_API_KEY, timeout=10.0)
        logger.info("Groq client initialised")
    except Exception as err:
        logger.warning("Failed to initialise Groq client: %s", err)
        _groq_client = None
    return _groq_client


def reset_groq_client() -> None:
    global _groq_client, _client_initialized
    _groq_client = None
    _client_initialized = False


def call_groq(prompt: str, system: str, model: str = "llama-3.3-70b-versatile", api_key: str = "") -> dict | None:
    effective_key = api_key or _request_api_key.get()
    if effective_key:
        try:
            import groq as _groq
            client: Any = _groq.Groq(api_key=effective_key, timeout=10.0)
        except Exception as err:
            logger.warning("Failed to create per-request Groq client: %s", err)
            return None
    else:
        client = get_groq_client()
    if client is None:
        return None
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1024,
            timeout=10,
        )
        if not response.choices:
            logger.warning("Groq returned empty choices")
            return None
        raw = response.choices[0].message.content or ""
        json_match = _extract_json_block(raw)
        if json_match is None:
            logger.warning("Groq response contained no parseable JSON block")
            return None
        return json_match
    except Exception as err:
        logger.error("Groq call failed: %s", err)
        return None


def _extract_json_block(text: str) -> dict | None:
    text = text.strip()
    fence_start = text.find("```json")
    if fence_start != -1:
        fence_end = text.find("```", fence_start + 3)
        text = text[fence_start + 7 : fence_end].strip()
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start == -1 or brace_end == -1:
        return None
    try:
        return json.loads(text[brace_start : brace_end + 1])
    except json.JSONDecodeError:
        return None
