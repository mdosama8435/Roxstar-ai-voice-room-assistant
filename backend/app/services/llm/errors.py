"""
Standardized error taxonomy and normalization for LLM providers.
Differentiates between retryable failures (eligible for fallback) and non-retryable failures.
"""

import asyncio
from typing import Optional, Set


class ErrorCategory:
    # Retryable failure categories
    RATE_LIMIT = "rate_limit"
    QUOTA_EXHAUSTED = "quota_exhausted"
    SERVICE_UNAVAILABLE = "service_unavailable"
    CONNECTION_FAILURE = "connection_failure"
    TIMEOUT = "timeout"

    # Non-retryable failure categories
    AUTHENTICATION = "authentication"
    INVALID_MODEL = "invalid_model"
    INVALID_REQUEST = "invalid_request"
    CANCELLATION = "cancellation"
    CONFIGURATION_ERROR = "configuration_error"
    UNKNOWN = "unknown"


RETRYABLE_CATEGORIES: Set[str] = {
    ErrorCategory.RATE_LIMIT,
    ErrorCategory.QUOTA_EXHAUSTED,
    ErrorCategory.SERVICE_UNAVAILABLE,
    ErrorCategory.CONNECTION_FAILURE,
    ErrorCategory.TIMEOUT,
}

NON_RETRYABLE_CATEGORIES: Set[str] = {
    ErrorCategory.AUTHENTICATION,
    ErrorCategory.INVALID_MODEL,
    ErrorCategory.INVALID_REQUEST,
    ErrorCategory.CANCELLATION,
    ErrorCategory.CONFIGURATION_ERROR,
    ErrorCategory.UNKNOWN,
}


class ProviderError(RuntimeError):
    """
    Standardized provider-neutral error representing failures in LLM interactions.
    Inherits from RuntimeError so existing error handlers catch it cleanly.
    """

    def __init__(
        self,
        provider: str,
        category: str,
        retryable: bool,
        message: str,
        status_code: Optional[int] = None,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(f"[{provider}] {category}: {message}")
        self.provider = provider
        self.category = category
        self.retryable = retryable
        self.message = message
        self.status_code = status_code
        self.original_error = original_error

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "category": self.category,
            "retryable": self.retryable,
            "message": self.message,
            "status_code": self.status_code,
        }


def classify_provider_error(provider: str, exc: Exception) -> ProviderError:
    """
    Normalizes any exception into a standardized ProviderError with retryable classification.
    """
    if isinstance(exc, ProviderError):
        return exc

    if isinstance(exc, asyncio.CancelledError):
        return ProviderError(
            provider=provider,
            category=ErrorCategory.CANCELLATION,
            retryable=False,
            message="Operation was cancelled",
            original_error=exc,
        )

    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return ProviderError(
            provider=provider,
            category=ErrorCategory.TIMEOUT,
            retryable=True,
            message="Request timed out",
            original_error=exc,
        )

    err_str = str(exc).lower()
    status_code = getattr(exc, "status_code", getattr(exc, "code", None))
    try:
        if status_code is not None:
            status_code = int(status_code)
    except (ValueError, TypeError):
        status_code = None

    # Quota / Rate limit (HTTP 429 / RESOURCE_EXHAUSTED)
    if status_code == 429 or "quota" in err_str or "resource_exhausted" in err_str or "rate limit" in err_str or "too many requests" in err_str:
        cat = ErrorCategory.QUOTA_EXHAUSTED if ("quota" in err_str or "resource_exhausted" in err_str) else ErrorCategory.RATE_LIMIT
        return ProviderError(
            provider=provider,
            category=cat,
            retryable=True,
            message=f"Rate limit / Quota exceeded: {str(exc)}",
            status_code=429,
            original_error=exc,
        )

    # Temporary Service Unavailable (HTTP 503 / 502 / 504)
    if status_code in (502, 503, 504) or "unavailable" in err_str or "bad gateway" in err_str or "gateway timeout" in err_str:
        return ProviderError(
            provider=provider,
            category=ErrorCategory.SERVICE_UNAVAILABLE,
            retryable=True,
            message=f"Service temporarily unavailable: {str(exc)}",
            status_code=status_code or 503,
            original_error=exc,
        )

    # Connection / Network error
    if "connection" in err_str or "network" in err_str or "dns" in err_str or "econnrefused" in err_str or "clientconnectorerror" in err_str:
        return ProviderError(
            provider=provider,
            category=ErrorCategory.CONNECTION_FAILURE,
            retryable=True,
            message=f"Transient connection failure: {str(exc)}",
            original_error=exc,
        )

    # Authentication / API key error (HTTP 401 / 403 / UNAUTHENTICATED / PERMISSION_DENIED)
    if status_code in (401, 403) or "unauthenticated" in err_str or "permission_denied" in err_str or "api key" in err_str or "unauthorized" in err_str or "invalid_api_key" in err_str:
        return ProviderError(
            provider=provider,
            category=ErrorCategory.AUTHENTICATION,
            retryable=False,
            message="Authentication or API key error",
            status_code=status_code or 401,
            original_error=exc,
        )

    # Invalid Model / Not Found (HTTP 404)
    if status_code == 404 or "model not found" in err_str or "not_found" in err_str:
        return ProviderError(
            provider=provider,
            category=ErrorCategory.INVALID_MODEL,
            retryable=False,
            message="Invalid or unsupported model",
            status_code=404,
            original_error=exc,
        )

    # Invalid / Malformed Request (HTTP 400)
    if status_code == 400 or "invalid argument" in err_str or "bad request" in err_str or "invalid_request" in err_str:
        return ProviderError(
            provider=provider,
            category=ErrorCategory.INVALID_REQUEST,
            retryable=False,
            message="Malformed or invalid request",
            status_code=400,
            original_error=exc,
        )

    # Default unknown / non-retryable
    return ProviderError(
        provider=provider,
        category=ErrorCategory.UNKNOWN,
        retryable=False,
        message=f"Unclassified provider error: {str(exc)}",
        status_code=status_code,
        original_error=exc,
    )
