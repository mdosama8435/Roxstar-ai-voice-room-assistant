"""
Vendor-agnostic base abstraction for LLM response generation providers.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator

from app.schemas.llm import LLMRequest, LLMResponse, LLMStreamChunk


class LLMProvider(ABC):
    """
    Abstract interface decoupling orchestration from concrete LLM vendor implementations.
    Every provider must support complete generation, incremental streaming, safe cancellation,
    and health status probes.
    """

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Executes non-streaming completion and returns the final LLMResponse.
        """
        pass

    @abstractmethod
    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        """
        Executes streaming completion, yielding incremental LLMStreamChunk fragments.
        """
        pass

    @abstractmethod
    async def cancel(self, request_id: str) -> None:
        """
        Signals cancellation of an active generation request by request_id.
        Must stop stream consumption and prevent downstream response publication.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Validates provider configuration and connectivity without leaking credentials.
        """
        pass
