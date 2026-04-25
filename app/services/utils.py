import logging
import re
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings

logger = logging.getLogger(__name__)

_INJECTION_PATTERNS = re.compile(
    r"ignore previous instructions|forget everything|you are now|"
    r"jailbreak|act as|pretend you|disregard|override",
    re.IGNORECASE,
)

_DANGEROUS_TAG_PATTERN = re.compile(r"<(script|style|iframe|object|embed)[^>]*>.*?</(script|style|iframe|object|embed)>", re.IGNORECASE | re.DOTALL)
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_CRLF_PATTERN = re.compile(r"[\r\n]")


def strip_html(value: str) -> str:
    cleaned = _DANGEROUS_TAG_PATTERN.sub("", value)
    cleaned = _HTML_TAG_PATTERN.sub("", cleaned)
    return cleaned.strip()


def sanitize_log_field(value: str) -> str:
    return _CRLF_PATTERN.sub(" ", value)


def contains_prompt_injection(text: str) -> bool:
    return bool(_INJECTION_PATTERNS.search(text))


def sanitize_text_input(value: str, max_length: int = 512) -> str:
    cleaned = strip_html(value)
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned


def create_access_token(data: dict) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload["exp"] = expire
    payload["iss"] = "iot-anomaly"
    payload["aud"] = "iot-anomaly-api"
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"require": ["exp", "iss", "aud"]},
        issuer="iot-anomaly",
        audience="iot-anomaly-api",
    )
