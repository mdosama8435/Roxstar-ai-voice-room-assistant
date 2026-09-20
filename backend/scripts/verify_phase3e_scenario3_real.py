"""Minimal real-Gemini check for Phase 3E Scenario 3 only (quota-conscious)."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

from dotenv import dotenv_values


def _load() -> None:
    for p in (BACKEND / ".env", ROOT / ".env"):
        for k, v in dotenv_values(p).items():
            if v is None:
                continue
            cur = os.environ.get(k, "")
            if cur and "placeholder" not in cur.lower() and (
                "placeholder" in v.lower() or v.lower().startswith("your_")
            ):
                continue
            os.environ[k] = v
    os.environ["LLM_PROVIDER"] = "gemini"
    os.environ["LLM_PRIMARY_PROVIDER"] = "gemini"


async def main() -> int:
    _load()

    from app.config import settings
    from app.schemas.contracts import ModalityType, TranscriptEvent
    from app.services.llm.factory import get_llm_provider
    from app.services.llm.gemini_provider import GeminiLLMProvider
    from app.services.llm.manager import LLMProviderManager
    from app.services.orchestrator import OrchestratorService
    from app.services.turn_lock import turn_lock_manager

    print("GEMINI_KEY", "YES" if settings.effective_gemini_api_key else "NO")
    provider = get_llm_provider()
    print("PROVIDER", type(provider).__name__)
    ok_type = isinstance(provider, (GeminiLLMProvider, LLMProviderManager))
    if not ok_type or not settings.effective_gemini_api_key:
        print("RESULT BLOCKED_NOT_GEMINI")
        return 2

    svc = OrchestratorService()
    room = "p3e-real-sc3"
    await turn_lock_manager.release(room)

    async def one(text: str, eid: str):
        evt = TranscriptEvent(
            event_id=eid,
            room_id=room,
            participant_identity="human-rahul",
            participant_display_name="Rahul",
            transcript=text,
            status="final",
            modality=ModalityType.TEXT,
            timestamp=datetime.now(timezone.utc),
        )
        dec = await svc.handle_transcript_event(evt)
        bot = getattr(getattr(dec, "routing", None), "selected_bot", None)
        print("DECISION", text[:48], "bot=", getattr(bot, "value", None))
        if not dec or not dec.turn_lock_acquired:
            return None
        resp = await svc.await_llm_response(dec.turn_id, timeout=45.0)
        if resp:
            print("RESP", resp.bot.value, resp.provider, (resp.text or "")[:200])
        else:
            print("RESP NONE")
        await turn_lock_manager.release(room)
        await asyncio.sleep(22)
        return resp

    r1 = await one("Shah Rukh Khan kaun hai?", "p3e-sc3-1")
    r2 = await one("Unki koi famous movie batao.", "p3e-sc3-2")
    ok = bool(
        r1
        and r2
        and any(
            k in (r2.text or "").lower()
            for k in (
                "film",
                "movie",
                "dilwale",
                "swades",
                "pathaan",
                "chennai",
                "shahrukh",
                "shah rukh",
                "srk",
                "khan",
            )
        )
    )
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
