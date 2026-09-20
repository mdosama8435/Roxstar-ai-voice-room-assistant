"""
Concrete LLMProvider implementation for NVIDIA NIM using the OpenAI-compatible Python SDK.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Set

import openai
from openai import AsyncOpenAI

from app.config import settings
from app.schemas.contracts import BotType
from app.schemas.llm import LLMRequest, LLMResponse, LLMStreamChunk
from app.services.llm.base import LLMProvider
from app.services.llm.errors import ProviderError, classify_provider_error

logger = logging.getLogger("roxstar.llm.nvidia")

_UNSET = object()


class NVIDIAProvider(LLMProvider):
    """
    Isolated NVIDIA NIM provider utilizing the OpenAI-compatible Python SDK.
    Dispatches to configured NVIDIA NIM endpoints (e.g. self-hosted NIM or NVIDIA API catalog).
    """

    name: str = "nvidia"

    def __init__(
        self,
        api_key: Any = _UNSET,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        if api_key is not _UNSET:
            self.api_key = api_key
        else:
            self.api_key = settings.effective_nvidia_api_key

        self.base_url = base_url or settings.nvidia_base_url or "https://integrate.api.nvidia.com/v1"
        self.default_model = default_model or settings.nvidia_model or "meta/llama-3.1-8b-instruct"
        self.timeout_seconds = timeout_seconds or settings.llm_timeout_seconds or 15.0

        self._cancelled_requests: Set[str] = set()
        self._active_tasks: Dict[str, asyncio.Task] = {}

        if self.api_key:
            self._client: Optional[AsyncOpenAI] = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout_seconds,
            )
        else:
            self._client = None

    def _ensure_client(self) -> AsyncOpenAI:
        if not self.api_key or not self._client:
            raise ProviderError(
                provider=self.name,
                category="configuration_error",
                retryable=False,
                message="NVIDIA_API_KEY is not configured or is a placeholder. Set NVIDIA_API_KEY in the environment.",
            )
        return self._client

    def _build_messages(self, request: LLMRequest) -> List[Dict[str, str]]:
        """
        Converts vendor-agnostic LLMRequest into OpenAI-compatible messages format.
        Maps 'model' role in context to 'assistant'.
        """
        messages: List[Dict[str, str]] = []

        # System prompt containing persona, safety, and constraints
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})

        # Multi-turn conversational context
        for msg in request.context_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            mapped_role = "assistant" if role in ("model", "assistant") else "user"
            messages.append({"role": mapped_role, "content": content})

        # Current user turn
        messages.append({"role": "user", "content": request.user_message})

        return messages

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        """
        Streams response chunks from NVIDIA NIM OpenAI-compatible endpoint.
        """
        if request.request_id in self._cancelled_requests:
            logger.info(f"NVIDIA stream {request.request_id} already marked cancelled; aborting")
            return

        client = self._ensure_client()
        model_name = request.model or self.default_model
        messages = self._build_messages(request)
        temperature = request.temperature if request.temperature is not None else settings.llm_temperature
        max_tokens = request.max_tokens if request.max_tokens is not None else settings.llm_max_output_tokens
        timeout_seconds = self.timeout_seconds

        current_task = asyncio.current_task()
        if current_task:
            self._active_tasks[request.request_id] = current_task

        logger.info(
            f"Initiating NVIDIA NIM stream for request {request.request_id} (model={model_name}, bot={request.selected_bot.value})"
        )

        try:
            response_stream = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                ),
                timeout=timeout_seconds,
            )

            sequence = 0
            async for chunk in response_stream:
                if request.request_id in self._cancelled_requests:
                    logger.info(f"NVIDIA stream {request.request_id} cancelled during consumption")
                    break

                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                text_delta = getattr(delta, "content", "") or ""

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
            logger.info(f"NVIDIA streaming task cancelled for request {request.request_id}")
            self._cancelled_requests.add(request.request_id)
            raise
        except asyncio.TimeoutError as timeout_err:
            logger.error(f"NVIDIA request timed out after {timeout_seconds}s for request {request.request_id}")
            raise classify_provider_error(self.name, timeout_err)
        except Exception as exc:
            if isinstance(exc, ProviderError):
                raise
            logger.error(f"Error during NVIDIA stream for request {request.request_id}: {type(exc).__name__}")
            raise classify_provider_error(self.name, exc)
        finally:
            self._active_tasks.pop(request.request_id, None)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Executes generation by streaming and aggregating full response.
        """
        t_start = time.perf_counter()
        accumulated_text: List[str] = []
        first_token_latency: Optional[float] = None

        async for chunk in self.stream(request):
            if first_token_latency is None and chunk.text_delta:
                first_token_latency = round((time.perf_counter() - t_start) * 1000.0, 2)
            accumulated_text.append(chunk.text_delta)

        full_text = "".join(accumulated_text).strip()
        total_latency = round((time.perf_counter() - t_start) * 1000.0, 2)

        return LLMResponse(
            request_id=request.request_id,
            bot=request.selected_bot,
            text=full_text,
            model=request.model or self.default_model,
            provider=self.name,
            finish_reason="stop",
            latency_ms=total_latency,
            first_token_latency_ms=first_token_latency,
            timestamp=datetime.now(timezone.utc),
        )

    async def cancel(self, request_id: str) -> None:
        """
        Signals cancellation of an active generation request.
        """
        logger.info(f"Signaling cancellation for NVIDIA request {request_id}")
        self._cancelled_requests.add(request_id)
        task = self._active_tasks.get(request_id)
        if task and not task.done():
            task.cancel()

    async def health_check(self) -> bool:
        """
        Validates provider configuration without leaking credentials.
        """
        return bool(self.api_key and self._client)
