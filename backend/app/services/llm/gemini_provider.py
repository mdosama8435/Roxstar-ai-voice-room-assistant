"""
Concrete LLMProvider implementation for Google Gemini API using official google-genai SDK.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, Optional, Set

from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.config import settings
from app.schemas.contracts import BotType
from app.schemas.llm import LLMRequest, LLMResponse, LLMStreamChunk
from app.services.llm.base import LLMProvider
from app.services.llm.errors import ProviderError, classify_provider_error

logger = logging.getLogger("roxstar.llm.gemini")


_UNSET = object()


class GeminiLLMProvider(LLMProvider):
    """
    Isolated Google Gemini API provider utilizing the official google-genai Python SDK.
    Never imports directly into orchestrator or leaks credentials to frontend.
    """
    name: str = "gemini"

    def __init__(
        self,
        api_key: Any = _UNSET,
        default_model: Optional[str] = None,
    ) -> None:
        if api_key is not _UNSET:
            self.api_key = api_key
        else:
            self.api_key = settings.effective_gemini_api_key
        self.default_model = default_model or settings.llm_model or "gemini-3.5-flash-lite"
        self._cancelled_requests: Set[str] = set()
        self._active_tasks: Dict[str, asyncio.Task] = {}

        if self.api_key:
            self._client = genai.Client(api_key=self.api_key)
        else:
            self._client = None

    def _ensure_client(self) -> genai.Client:
        if not self.api_key or not self._client:
            raise ValueError(
                "GEMINI_API_KEY is not configured or is a placeholder. "
                "Set GEMINI_API_KEY in the backend environment."
            )
        return self._client

    def _build_contents(self, request: LLMRequest):
        """
        Builds contents list preserving multi-turn context and current user message.
        """
        contents = []
        # Multi-turn history if present
        for msg in request.context_messages:
            role = "user" if msg.get("role") == "user" else "model"
            content_text = msg.get("content", "")
            if content_text:
                contents.append(types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=content_text)]
                ))

        # Current user utterance
        contents.append(types.Content(
            role="user",
            parts=[types.Part.from_text(text=request.user_message)]
        ))
        return contents

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        """
        Streams response chunks from Google Gemini using client.aio.models.generate_content_stream.
        """
        client = self._ensure_client()
        model_name = request.model or self.default_model

        if request.request_id in self._cancelled_requests:
            logger.info(f"Gemini request {request.request_id} already cancelled before streaming")
            return

        config = types.GenerateContentConfig(
            temperature=request.temperature if request.temperature is not None else settings.llm_temperature,
            max_output_tokens=request.max_tokens if request.max_tokens is not None else settings.llm_max_output_tokens,
            system_instruction=request.system_prompt,
        )

        contents = self._build_contents(request)
        timeout_seconds = settings.llm_timeout_seconds

        try:
            # Current task tracking for cancellation
            current_task = asyncio.current_task()
            if current_task:
                self._active_tasks[request.request_id] = current_task

            logger.info(
                f"Initiating Gemini stream for request {request.request_id} (model={model_name}, bot={request.selected_bot.value})"
            )

            response_stream = await asyncio.wait_for(
                client.aio.models.generate_content_stream(
                    model=model_name,
                    contents=contents,
                    config=config,
                ),
                timeout=timeout_seconds,
            )

            sequence = 0
            async for chunk in response_stream:
                if request.request_id in self._cancelled_requests:
                    logger.info(f"Gemini stream {request.request_id} cancelled during chunk consumption")
                    break

                text_delta = chunk.text or ""
                if text_delta:
                    yield LLMStreamChunk(
                        request_id=request.request_id,
                        bot=request.selected_bot,
                        text_delta=text_delta,
                        sequence=sequence,
                        timestamp=datetime.now(timezone.utc),
                        is_final=False,
                    )
                    sequence += 1

        except asyncio.CancelledError:
            logger.info(f"Gemini streaming task cancelled for request {request.request_id}")
            self._cancelled_requests.add(request.request_id)
            raise
        except asyncio.TimeoutError as timeout_err:
            logger.error(f"Gemini request timed out after {timeout_seconds}s for request {request.request_id}")
            raise classify_provider_error("gemini", timeout_err)
        except APIError as api_err:
            # Sanitize error message to avoid credential exposure
            status_code = getattr(api_err, "code", "unknown")
            logger.error(
                f"Gemini APIError ({status_code}) during streaming for request {request.request_id}: {str(api_err.message if hasattr(api_err, 'message') else api_err)}"
            )
            raise classify_provider_error("gemini", api_err)
        except Exception as exc:
            if isinstance(exc, ProviderError):
                raise
            logger.error(
                f"Unexpected error in Gemini stream for request {request.request_id}: {type(exc).__name__}"
            )
            raise classify_provider_error("gemini", exc)
        finally:
            self._active_tasks.pop(request.request_id, None)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Generates full non-streaming response by aggregating stream chunks.
        """
        t_start = time.perf_counter()
        accumulated_text: list[str] = []
        first_token_latency: Optional[float] = None

        async for chunk in self.stream(request):
            if first_token_latency is None:
                first_token_latency = round((time.perf_counter() - t_start) * 1000.0, 2)
            accumulated_text.append(chunk.text_delta)

        t_complete = time.perf_counter()
        total_latency_ms = round((t_complete - t_start) * 1000.0, 2)
        full_text = "".join(accumulated_text).strip()

        return LLMResponse(
            request_id=request.request_id,
            bot=request.selected_bot,
            text=full_text,
            model=request.model or self.default_model,
            provider="gemini",
            finish_reason="stop" if request.request_id not in self._cancelled_requests else "cancelled",
            latency_ms=total_latency_ms,
            first_token_latency_ms=first_token_latency,
            token_count=None,
            timestamp=datetime.now(timezone.utc),
        )

    async def cancel(self, request_id: str) -> None:
        """
        Safely cancels local consumption task and registers cancellation state.
        """
        self._cancelled_requests.add(request_id)
        task = self._active_tasks.pop(request_id, None)
        if task and not task.done():
            logger.info(f"Cancelling active async task for request {request_id}")
            task.cancel()

    async def health_check(self) -> bool:
        """
        Verifies client configuration readiness.
        """
        return bool(self.api_key and "placeholder" not in self.api_key.lower())
