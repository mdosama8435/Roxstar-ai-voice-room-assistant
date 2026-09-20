import datetime
import json
import logging
import re
import sys
from typing import Any, Dict, Optional

# Secret patterns to mask
_SECRET_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|secret|token|password|auth|authorization)["\']?\s*[:=]\s*["\']?([^"\'\s]+)'),
]

def sanitize_data(data: Any) -> Any:
    """Recursively scrub secrets, tokens, and credentials from log dictionaries."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(term in k_lower for term in ("key", "secret", "token", "password", "auth", "credential")):
                sanitized[k] = "[REDACTED]"
            elif k_lower in ("audio", "raw_audio", "audio_buffer", "pcm_bytes"):
                sanitized[k] = f"[AUDIO_BUFFER_OMITTED length={len(v) if hasattr(v, '__len__') else 'unknown'}]"
            else:
                sanitized[k] = sanitize_data(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_data(item) for item in data]
    elif isinstance(data, str):
        # Mask raw string patterns
        masked = data
        for pattern in _SECRET_PATTERNS:
            masked = pattern.sub(r'\1: [REDACTED]', masked)
        return masked
    return data


class StructuredLogFormatter(logging.Formatter):
    """Formats log records as structured JSON."""
    def format(self, record: logging.LogRecord) -> str:
        log_payload: Dict[str, Any] = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitize_data(record.getMessage()),
        }

        # Contextual metadata
        for attr in ("request_id", "room_id", "participant_id", "event_type", "duration_ms"):
            if hasattr(record, attr):
                log_payload[attr] = getattr(record, attr)

        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict): # type: ignore
            log_payload["data"] = sanitize_data(record.extra_data) # type: ignore

        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_payload)


def setup_structured_logger(name: str = "roxstar", level: Optional[str] = None) -> logging.Logger:
    """Configures and returns a structured JSON logger. Respects LOG_LEVEL when provided."""
    resolved = (level or "INFO").upper()
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, resolved, logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredLogFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    else:
        # Keep existing handlers; update level when reconfigured at startup
        logger.setLevel(getattr(logging, resolved, logging.INFO))

    return logger


# Default application logger
app_logger = setup_structured_logger()
get_logger = setup_structured_logger


class MetricsCollectorInterface:
    """
    Protocol/Interface for recording pipeline latency and counter metrics.
    In Phase 1, this defines the contract without recording fake metrics.
    """
    def record_latency(self, metric_name: str, duration_ms: float, tags: Optional[Dict[str, str]] = None) -> None:
        raise NotImplementedError

    def increment_counter(self, metric_name: str, count: int = 1, tags: Optional[Dict[str, str]] = None) -> None:
        raise NotImplementedError
