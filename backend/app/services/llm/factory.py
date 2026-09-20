"""
Factory for instantiating LLM providers and the failover provider manager.
"""

import logging
from typing import Optional

from app.config import settings
from app.services.llm.base import LLMProvider
from app.services.llm.gemini_provider import GeminiLLMProvider
from app.services.llm.manager import LLMProviderManager
from app.services.llm.mock_provider import MockLLMProvider
from app.services.llm.nvidia_provider import NVIDIAProvider

logger = logging.getLogger("roxstar.llm.factory")


def create_concrete_provider(
    provider_name: str,
    api_key_override: Optional[str] = None,
    model_override: Optional[str] = None,
    require_configured: bool = True,
) -> LLMProvider:
    """
    Creates a concrete standalone provider instance without manager wrapping.
    """
    p_name = provider_name.lower().strip()

    if p_name == "gemini":
        key = api_key_override if api_key_override is not None else settings.effective_gemini_api_key
        if require_configured and (not key or not str(key).strip() or str(key).strip() in ("your_gemini_api_key_here", "placeholder")):
            raise ValueError(
                "GEMINI_API_KEY is not configured while LLM provider is 'gemini'. "
                "Explicitly set GEMINI_API_KEY or configure LLM_PRIMARY_PROVIDER=mock."
            )
        return GeminiLLMProvider(
            api_key=key,
            default_model=model_override or settings.llm_model,
        )

    if p_name == "nvidia":
        key = api_key_override if api_key_override is not None else settings.effective_nvidia_api_key
        if require_configured and (not key or not str(key).strip() or str(key).strip() in ("your_nvidia_nim_api_key_placeholder", "placeholder")):
            raise ValueError(
                "NVIDIA_API_KEY is not configured while LLM provider is 'nvidia'. "
                "Explicitly set NVIDIA_API_KEY or configure LLM_PRIMARY_PROVIDER=mock."
            )
        return NVIDIAProvider(
            api_key=key,
            base_url=settings.nvidia_base_url,
            default_model=model_override or settings.nvidia_model,
        )

    if p_name in ("mock", "test"):
        return MockLLMProvider()

    raise ValueError(
        f"Unsupported LLM provider: '{provider_name}'. "
        "Supported providers are 'gemini', 'nvidia', and 'mock'."
    )


def get_llm_provider(
    provider_override: Optional[str] = None,
    api_key_override: Optional[str] = None,
    model_override: Optional[str] = None,
) -> LLMProvider:
    """
    Returns configured LLMProvider instance.
    - If provider_override is specified: returns the concrete provider directly.
    - If no override: returns LLMProviderManager configured with primary & fallback providers.
    """
    # 1. Direct explicit override
    if provider_override:
        return create_concrete_provider(
            provider_name=provider_override,
            api_key_override=api_key_override,
            model_override=model_override,
            require_configured=True,
        )

    # 2. Mock mode bypass
    primary_name = settings.effective_primary_provider
    if primary_name in ("mock", "test"):
        return MockLLMProvider()

    # 3. Create primary provider
    primary_provider = create_concrete_provider(
        provider_name=primary_name,
        api_key_override=api_key_override,
        model_override=model_override,
        require_configured=True,
    )

    # 4. Create fallback provider if enabled
    fallback_provider: Optional[LLMProvider] = None
    if settings.llm_enable_fallback:
        fallback_name = settings.effective_fallback_provider
        if fallback_name != primary_name:
            if settings.is_fallback_configured:
                try:
                    fallback_provider = create_concrete_provider(
                        provider_name=fallback_name,
                        require_configured=True,
                    )
                    logger.info(f"LLM fallback provider '{fallback_name}' initialized and available")
                except Exception as fb_err:
                    logger.warning(f"Fallback provider '{fallback_name}' could not be initialized: {fb_err}")
                    fallback_provider = None
            else:
                logger.info(f"LLM fallback provider '{fallback_name}' credentials missing; fallback disabled at runtime")

    return LLMProviderManager(
        primary_provider=primary_provider,
        fallback_provider=fallback_provider,
        fallback_enabled=settings.llm_enable_fallback,
    )
