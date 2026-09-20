"""
Opt-in live smoke test for real NVIDIA NIM endpoint (Requirement 20).
Executes only when NVIDIA_API_KEY, NVIDIA_BASE_URL, and NVIDIA_MODEL are configured in the environment.
"""

import os
import pytest

from app.config import settings
from app.schemas.contracts import BotType
from app.schemas.llm import LLMRequest
from app.services.llm.nvidia_provider import NVIDIAProvider
from app.services.llm.output_validator import OutputValidator
from app.services.personas.dost import AI_DOST_SYSTEM_INSTRUCTIONS


def is_nvidia_live_configured() -> bool:
    return bool(
        settings.effective_nvidia_api_key
        and settings.nvidia_base_url
        and settings.nvidia_model
        and os.getenv("RUN_LLM_LIVE_TEST") == "true"
    )


@pytest.mark.asyncio
@pytest.mark.skipif(
    not is_nvidia_live_configured(),
    reason="Opt-in real NVIDIA test requires RUN_LLM_LIVE_TEST=true and valid NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODEL",
)
async def test_real_nvidia_live_smoke_ai_explanation():
    """
    Live test 1: "AI kya hota hai? Simple Hinglish mein batao."
    Verifies real NVIDIA NIM connection, streaming, and latency.
    """
    provider = NVIDIAProvider()
    req = LLMRequest(
        request_id="nvidia-live-ai-1",
        room_id="live-nvidia-room",
        participant_identity="tester",
        selected_bot=BotType.DOST,
        turn_id="turn-nv-1",
        user_message="AI kya hota hai? Simple Hinglish mein batao.",
        system_prompt=AI_DOST_SYSTEM_INSTRUCTIONS,
    )

    chunks = []
    async for chunk in provider.stream(req):
        chunks.append(chunk.text_delta)

    full_text = "".join(chunks).strip()
    assert len(full_text) > 10, "Expected substantive response from real NVIDIA NIM"
    validated = OutputValidator.validate(full_text)
    assert len(validated) > 10

    resp = await provider.generate(req)
    assert resp.provider == "nvidia"
    assert resp.model == settings.nvidia_model
    assert resp.latency_ms > 0
    assert len(resp.text) > 10


@pytest.mark.asyncio
@pytest.mark.skipif(
    not is_nvidia_live_configured(),
    reason="Opt-in real NVIDIA test requires RUN_LLM_LIVE_TEST=true and valid NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODEL",
)
async def test_real_nvidia_live_smoke_cloud_computing():
    """
    Live test 2: "Cloud computing kya hoti hai? Hindi mein simple example ke saath samjhao."
    Verifies second distinct prompt on real NVIDIA NIM.
    """
    provider = NVIDIAProvider()
    req = LLMRequest(
        request_id="nvidia-live-cloud-2",
        room_id="live-nvidia-room",
        participant_identity="tester",
        selected_bot=BotType.DOST,
        turn_id="turn-nv-2",
        user_message="Cloud computing kya hoti hai? Hindi mein simple example ke saath samjhao.",
        system_prompt=AI_DOST_SYSTEM_INSTRUCTIONS,
    )

    resp = await provider.generate(req)
    assert resp.provider == "nvidia"
    assert resp.model == settings.nvidia_model
    assert resp.latency_ms > 0
    assert len(resp.text) > 10
