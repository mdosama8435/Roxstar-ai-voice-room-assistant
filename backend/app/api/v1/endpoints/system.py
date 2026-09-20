import sys
import platform
from datetime import datetime, timezone
from fastapi import APIRouter
from pydantic import BaseModel, Field
from app.config import settings

router = APIRouter()


class ProviderConfigStatus(BaseModel):
    livekit_configured: bool = Field(..., description="Whether LiveKit credentials are present")
    sarvam_configured: bool = Field(..., description="Whether Sarvam API key is present")
    llm_configured: bool = Field(..., description="Whether primary LLM API key is present")
    database_configured: bool = Field(..., description="Whether Database URL is present")
    redis_configured: bool = Field(..., description="Whether Redis URL is present")

    # Phase 3C.1 LLM Failover Diagnostics
    primary_provider: str = Field(default="gemini", description="Configured primary LLM provider")
    fallback_provider: str = Field(default="nvidia", description="Configured fallback LLM provider")
    fallback_enabled: bool = Field(default=True, description="Whether LLM fallback is enabled")
    primary_configured: bool = Field(default=False, description="Whether primary provider has valid credentials")
    fallback_configured: bool = Field(default=False, description="Whether fallback provider has valid credentials")


class SystemStatusResponse(BaseModel):
    status: str = Field("operational", description="Backend service health status")
    service: str = Field(settings.app_name, description="Service name")
    version: str = Field(settings.app_version, description="Service semantic version")
    phase: str = Field("Phase 1: Foundation", description="Current implementation phase")
    python_version: str = Field(..., description="Runtime Python version")
    platform: str = Field(..., description="Host OS platform")
    environment: str = Field(settings.environment, description="Environment mode")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    providers: ProviderConfigStatus


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status() -> SystemStatusResponse:
    """
    Returns REAL backend status and provider configuration presence flags.
    Never exposes API secrets or fakes external provider connections.
    """
    prim_name = settings.effective_primary_provider
    fb_name = settings.effective_fallback_provider

    return SystemStatusResponse(
        status="operational",
        service=settings.app_name,
        version=settings.app_version,
        phase="Phase 1: Foundation",
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        platform=platform.system(),
        environment=settings.environment,
        providers=ProviderConfigStatus(
            livekit_configured=settings.is_provider_configured("livekit"),
            sarvam_configured=settings.is_provider_configured("sarvam"),
            llm_configured=settings.is_provider_configured("llm"),
            database_configured=settings.is_provider_configured("database"),
            redis_configured=settings.is_provider_configured("redis"),
            primary_provider=prim_name,
            fallback_provider=fb_name,
            fallback_enabled=settings.llm_enable_fallback,
            primary_configured=settings.is_provider_configured(prim_name),
            fallback_configured=settings.is_fallback_configured,
        )
    )
