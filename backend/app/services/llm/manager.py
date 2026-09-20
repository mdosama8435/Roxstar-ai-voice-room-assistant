"""
Resilient LLM Provider Manager providing controlled primary-to-fallback failover.
Implements the vendor-agnostic LLMProvider contract, keeping the orchestrator decoupled.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Set

from app.config import settings
from app.schemas.llm import LLMRequest, LLMResponse, LLMStreamChunk
from app.services.llm.base import LLMProvider
from app.services.llm.errors import ErrorCategory, ProviderError, classify_provider_error

logger = logging.getLogger("roxstar.llm.manager")


class LLMProviderManager(LLMProvider):
    """
    Master provider coordinator managing primary invocation, retryable failure classification,
    and controlled fallback execution while preserving multi-turn context and single canonical response.
    """

    def __init__(
        self,
        primary_provider: LLMProvider,
        fallback_provider: Optional[LLMProvider] = None,
        fallback_enabled: bool = True,
    ) -> None:
        self.primary_provider = primary_provider
        self.fallback_provider = fallback_provider
        self.fallback_enabled = fallback_enabled
        self._cancelled_requests: Set[str] = set()
        self._request_metadata: Dict[str, Dict[str, Any]] = {}

    @property
    def primary_name(self) -> str:
        return getattr(self.primary_provider, "name", type(self.primary_provider).__name__)

    @property
    def fallback_name(self) -> Optional[str]:
        if not self.fallback_provider:
            return None
        return getattr(self.fallback_provider, "name", type(self.fallback_provider).__name__)

    def get_metadata(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves observability metrics and failover trajectory for a request."""
        return self._request_metadata.get(request_id)

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        """
        Streams response tokens, falling back to secondary provider if primary encounters a retryable error.
        Guarantees:
        - Max 2 provider attempts per request.
        - No fallback loops.
        - Cancellation suppresses fallback.
        - Exactly one canonical stream is delivered.
        """
        if request.request_id in self._cancelled_requests:
            logger.info(f"Manager request {request.request_id} already marked cancelled; aborting stream")
            return

        t_start = time.perf_counter()
        meta: Dict[str, Any] = {
            "request_id": request.request_id,
            "turn_id": request.turn_id,
            "primary_provider": self.primary_name,
            "fallback_enabled": self.fallback_enabled,
            "primary_attempt_started": datetime.now(timezone.utc).isoformat(),
            "primary_attempt_finished": None,
            "primary_failure_category": None,
            "fallback_triggered": False,
            "fallback_provider": self.fallback_name,
            "fallback_attempt_started": None,
            "fallback_attempt_finished": None,
            "final_provider": self.primary_name,
            "time_to_first_token_ms": None,
            "total_generation_ms": None,
        }
        self._request_metadata[request.request_id] = meta

        primary_failed = False
        primary_error: Optional[ProviderError] = None
        chunks_yielded = 0
        t_first_token: Optional[float] = None

        # ----------------------------------------------------------------------
        # ATTEMPT 1: Primary Provider
        # ----------------------------------------------------------------------
        try:
            logger.info(f"Calling primary provider '{self.primary_name}' for request {request.request_id}")
            async for chunk in self.primary_provider.stream(request):
                if request.request_id in self._cancelled_requests:
                    logger.info(f"Stream cancelled during primary consumption: {request.request_id}")
                    return

                if t_first_token is None and chunk.text_delta:
                    t_first_token = time.perf_counter()
                    meta["time_to_first_token_ms"] = round((t_first_token - t_start) * 1000.0, 2)

                chunks_yielded += 1
                yield chunk

            meta["primary_attempt_finished"] = datetime.now(timezone.utc).isoformat()
            meta["final_provider"] = self.primary_name
            meta["total_generation_ms"] = round((time.perf_counter() - t_start) * 1000.0, 2)
            return

        except asyncio.CancelledError:
            logger.info(f"Cancellation during primary provider stream for {request.request_id}")
            self._cancelled_requests.add(request.request_id)
            meta["primary_failure_category"] = ErrorCategory.CANCELLATION
            raise
        except Exception as exc:
            primary_failed = True
            primary_error = classify_provider_error(self.primary_name, exc)
            meta["primary_attempt_finished"] = datetime.now(timezone.utc).isoformat()
            meta["primary_failure_category"] = primary_error.category
            logger.warning(
                f"Primary provider '{self.primary_name}' failed for request {request.request_id} "
                f"(category={primary_error.category}, retryable={primary_error.retryable}, chunks_yielded={chunks_yielded})"
            )

        # ----------------------------------------------------------------------
        # EVALUATE FALLBACK ELIGIBILITY
        # ----------------------------------------------------------------------
        if not primary_failed or not primary_error:
            return

        # Check cancellation
        if request.request_id in self._cancelled_requests:
            logger.info(f"Request {request.request_id} was cancelled; suppressing fallback")
            raise primary_error

        # Check fallback allowed
        can_fallback = (
            self.fallback_enabled
            and primary_error.retryable
            and self.fallback_provider is not None
            and chunks_yielded == 0  # Only fallback if room hasn't received partial chunks
        )

        if not can_fallback:
            if not self.fallback_enabled:
                logger.info(f"Fallback disabled by configuration; propagating primary error for {request.request_id}")
            elif not primary_error.retryable:
                logger.info(f"Primary error '{primary_error.category}' is non-retryable; propagating error without fallback")
            elif not self.fallback_provider:
                logger.warning(f"Fallback provider unavailable/not configured; cannot fallback for {request.request_id}")
            elif chunks_yielded > 0:
                logger.warning(f"Primary provider failed mid-stream after yielding {chunks_yielded} chunks; cannot fallback cleanly")
            raise primary_error

        # ----------------------------------------------------------------------
        # ATTEMPT 2: Fallback Provider (ONE attempt max, no loops)
        # ----------------------------------------------------------------------
        meta["fallback_triggered"] = True
        meta["fallback_attempt_started"] = datetime.now(timezone.utc).isoformat()
        fallback_name = self.fallback_name or "fallback"
        logger.info(
            f"Failing over to fallback provider '{fallback_name}' for request {request.request_id} "
            f"(reason: primary '{self.primary_name}' error={primary_error.category})"
        )

        try:
            t_fb_start = time.perf_counter()
            async for chunk in self.fallback_provider.stream(request):
                if request.request_id in self._cancelled_requests:
                    logger.info(f"Stream cancelled during fallback consumption: {request.request_id}")
                    return

                if t_first_token is None and chunk.text_delta:
                    t_first_token = time.perf_counter()
                    meta["time_to_first_token_ms"] = round((t_first_token - t_start) * 1000.0, 2)

                yield chunk

            meta["fallback_attempt_finished"] = datetime.now(timezone.utc).isoformat()
            meta["final_provider"] = fallback_name
            meta["total_generation_ms"] = round((time.perf_counter() - t_start) * 1000.0, 2)
            logger.info(f"Fallback provider '{fallback_name}' succeeded for request {request.request_id}")
            return

        except asyncio.CancelledError:
            logger.info(f"Cancellation during fallback provider stream for {request.request_id}")
            self._cancelled_requests.add(request.request_id)
            raise
        except Exception as fb_exc:
            fb_err = classify_provider_error(fallback_name, fb_exc)
            meta["fallback_attempt_finished"] = datetime.now(timezone.utc).isoformat()
            logger.error(
                f"Fallback provider '{fallback_name}' also failed for request {request.request_id}: {fb_err.category}"
            )
            # Both attempts exhausted; propagate normalized failure without loops
            raise fb_err

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Executes non-streaming completion with identical failover logic.
        """
        accumulated_text: List[str] = []
        first_token_latency: Optional[float] = None
        t_start = time.perf_counter()

        async for chunk in self.stream(request):
            if first_token_latency is None and chunk.text_delta:
                first_token_latency = round((time.perf_counter() - t_start) * 1000.0, 2)
            accumulated_text.append(chunk.text_delta)

        full_text = "".join(accumulated_text).strip()
        total_latency = round((time.perf_counter() - t_start) * 1000.0, 2)

        meta = self.get_metadata(request.request_id) or {}
        final_provider = meta.get("final_provider", self.primary_name)

        return LLMResponse(
            request_id=request.request_id,
            bot=request.selected_bot,
            text=full_text,
            model=request.model or getattr(self.primary_provider, "default_model", settings.llm_model),
            provider=final_provider,
            finish_reason="stop",
            latency_ms=total_latency,
            first_token_latency_ms=first_token_latency,
            timestamp=datetime.now(timezone.utc),
        )

    async def cancel(self, request_id: str) -> None:
        """
        Cancels active request across both providers.
        """
        logger.info(f"Manager cancelling request {request_id}")
        self._cancelled_requests.add(request_id)
        if self.primary_provider:
            await self.primary_provider.cancel(request_id)
        if self.fallback_provider:
            await self.fallback_provider.cancel(request_id)

    async def health_check(self) -> bool:
        """
        Validates that primary provider is operational.
        """
        if not self.primary_provider:
            return False
        return await self.primary_provider.health_check()
