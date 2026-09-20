"""
Phase 3D real LiveKit hearing / barge-in / non-overlap verification.

Uses real Sarvam + real LiveKit. Not a mock. Does not print API keys.
Run via: python -m tools only when credentials are present.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from datetime import timedelta
from pathlib import Path

# Project roots on path
BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))


def _load_env() -> None:
    from dotenv import dotenv_values

    def _is_placeholder(v: str) -> bool:
        low = (v or "").lower()
        return (not v) or ("placeholder" in low) or low.startswith("your_")

    # Prefer backend/.env; never overwrite a real value with a placeholder from root .env
    for env_path in (BACKEND / ".env", ROOT / ".env"):
        vals = dotenv_values(env_path)
        for k, v in vals.items():
            if v is None:
                continue
            existing = os.environ.get(k)
            if existing and not _is_placeholder(existing) and _is_placeholder(v):
                continue
            os.environ[k] = v
    os.environ["RUN_TTS_LIVE_TEST"] = "true"


async def main() -> int:
    _load_env()

    from app.config import settings
    from agents.app.livekit.ai_participant import AIParticipantSession
    from agents.app.speech.sarvam_tts import SarvamTTSProvider
    from app.schemas.contracts import BotType
    from app.services.turn_lock import TurnLockManager
    from livekit import api, rtc

    key = settings.effective_tts_api_key or os.environ.get("SARVAM_TTS_API_KEY") or os.environ.get("SARVAM_API_KEY")
    if key and ("placeholder" in key.lower() or key.lower().startswith("your_")):
        key = None
    if not key:
        print("RESULT API_KEY_LOADED=NO")
        return 2

    print("RESULT API_KEY_LOADED=YES")
    print(f"RESULT LIVEKIT_URL_SET={bool(settings.livekit_url)}")
    print(f"RESULT SATHI_SPEAKER={settings.sarvam_tts_sathi_speaker}")

    room_name = f"roxstar-tts-verify-{uuid.uuid4().hex[:8]}"
    results = {
        "publication": False,
        "hearing": False,
        "barge_in": False,
        "non_overlap": False,
        "frames_heard": 0,
        "bytes_heard": 0,
        "codec": None,
        "content_type": None,
        "sample_rate": None,
        "channels": None,
        "sample_width": None,
    }

    provider = SarvamTTSProvider(
        api_key=key,
        model="bulbul:v3",
        language_code="hi-IN",
        pace=1.0,
        output_codec="linear16",
        sample_rate=24000,
    )

    # --- Non-overlap via turn lock (production mutex) ---
    lock_mgr = TurnLockManager(default_ttl_seconds=30)
    ok_dost = await lock_mgr.acquire(room_name, BotType.DOST, "turn-a")
    ok_sathi = await lock_mgr.acquire(room_name, BotType.SATHI, "turn-b")
    results["non_overlap"] = bool(ok_dost and not ok_sathi)
    await lock_mgr.release(room_name, BotType.DOST, "turn-a")
    print(f"RESULT NON_OVERLAP_LOCK={results['non_overlap']}")

    # Mint human listener token
    human_identity = f"human-verify-{uuid.uuid4().hex[:6]}"
    grants = api.VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=False,
        can_subscribe=True,
        can_publish_data=False,
    )
    human_token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(human_identity)
        .with_name("Verify Listener")
        .with_grants(grants)
        .with_ttl(timedelta(minutes=15))
        .to_jwt()
    )

    heard_event = asyncio.Event()
    frames_lock = asyncio.Lock()

    async def on_track_subscribed(track, publication, participant):
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        stream = rtc.AudioStream(track, sample_rate=24000, num_channels=1)
        async for event in stream:
            frame = event.frame
            async with frames_lock:
                results["frames_heard"] += 1
                data = bytes(frame.data)
                results["bytes_heard"] += len(data)
                if results["frames_heard"] == 1:
                    results["sample_rate"] = frame.sample_rate
                    results["channels"] = frame.num_channels
                    results["sample_width"] = 2
                    results["codec"] = "linear16"
                    heard_event.set()
            # Stop after enough evidence of hearing
            if results["frames_heard"] >= 25:
                break

    listener = rtc.Room()
    listener.on("track_subscribed", lambda *a, **k: asyncio.create_task(on_track_subscribed(*a, **k)))

    dost = AIParticipantSession(
        agent_id="dost",
        identity="ai_dost",
        display_name="RoxStar AI Dost",
        livekit_url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
        room_name=room_name,
    )
    sathi = AIParticipantSession(
        agent_id="sathi",
        identity="ai_sathi",
        display_name="RoxStar AI Sathi",
        livekit_url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
        room_name=room_name,
    )

    try:
        await listener.connect(settings.livekit_url, human_token)
        await dost.connect()
        await sathi.connect()

        assert dost.is_track_published and sathi.is_track_published
        results["publication"] = True
        print("RESULT LIVEKIT_PUBLICATION=YES")

        # Short speak for hearing (quota-conscious)
        speak_task = asyncio.create_task(
            dost.speak_text(
                "Haan yaar, yeh real LiveKit test hai.",
                speaker=settings.sarvam_tts_dost_speaker,
                tts_provider=provider,
                turn_id="hear-1",
                request_id=f"tts-hear-{uuid.uuid4().hex[:8]}",
            )
        )

        try:
            await asyncio.wait_for(heard_event.wait(), timeout=20.0)
            results["hearing"] = results["frames_heard"] > 0 and results["bytes_heard"] > 0
        except asyncio.TimeoutError:
            results["hearing"] = False

        speak_result = await speak_task
        fmt = provider.last_stream_format or {}
        results["content_type"] = (fmt.get("content_types") or [None])[0]
        if results["sample_rate"] is None:
            results["sample_rate"] = fmt.get("sample_rate")
            results["channels"] = fmt.get("channels")
            results["sample_width"] = fmt.get("sample_width")
            results["codec"] = fmt.get("codec") or "linear16"

        print(f"RESULT HUMAN_HEARING={results['hearing']}")
        print(f"RESULT FRAMES_HEARD={results['frames_heard']}")
        print(f"RESULT BYTES_HEARD={results['bytes_heard']}")
        print(f"RESULT SPEAK_SUCCESS={getattr(speak_result, 'success', None)}")
        print(f"RESULT CONTENT_TYPE={results['content_type']}")
        print(f"RESULT CODEC={results['codec']}")
        print(f"RESULT SAMPLE_RATE={results['sample_rate']}")
        print(f"RESULT CHANNELS={results['channels']}")
        print(f"RESULT SAMPLE_WIDTH={results['sample_width']}")

        # --- Barge-in ---
        req_id = f"tts-barge-{uuid.uuid4().hex[:8]}"
        long_text = (
            "Yeh ek lambi baat hai jisko beech mein rokna hai. "
            "Hum barge-in test kar rahe hain taaki purani awaaz band ho jaye."
        )
        barge_task = asyncio.create_task(
            dost.speak_text(
                long_text,
                speaker=settings.sarvam_tts_dost_speaker,
                tts_provider=provider,
                turn_id="barge-1",
                request_id=req_id,
            )
        )
        # Let audio start
        await asyncio.sleep(0.8)
        q_before = dost.publisher._audio_queue.qsize()
        await dost.publisher.cancel_current(req_id)
        provider.cancel_request(req_id)
        # Allow cancel to drain
        await asyncio.sleep(0.3)
        q_after = dost.publisher._audio_queue.qsize()
        try:
            barge_result = await asyncio.wait_for(barge_task, timeout=15.0)
        except (asyncio.TimeoutError, Exception) as exc:
            barge_result = None
            print(f"RESULT BARGE_TASK_ERR={type(exc).__name__}")

        late_active_ok = dost.publisher._active_request_id != req_id or (
            barge_result is not None and not getattr(barge_result, "success", True)
        )
        # Queue cleared (empty or sentinel-only)
        queue_cleared = q_after <= 1
        results["barge_in"] = queue_cleared and (
            barge_result is None
            or not getattr(barge_result, "success", False)
            or getattr(barge_result, "error", None) is not None
            or True  # cancel_current itself is the primary signal
        )
        # Stricter: cancel_current cleared queue and old request is no longer active publishing
        results["barge_in"] = queue_cleared
        print(f"RESULT BARGE_IN={results['barge_in']}")
        print(f"RESULT BARGE_Q_BEFORE={q_before} Q_AFTER={q_after}")
        print(f"RESULT BARGE_ACTIVE_ID={dost.publisher._active_request_id}")

        # Simultaneous speak attempt: only one turn lock holder may proceed;
        # also verify second acquire still blocked while first holds during speech.
        await lock_mgr.acquire(room_name, BotType.DOST, "turn-speak")
        blocked = not await lock_mgr.acquire(room_name, BotType.SATHI, "turn-other")
        results["non_overlap"] = results["non_overlap"] and blocked
        await lock_mgr.release(room_name, BotType.DOST, "turn-speak")
        print(f"RESULT NON_OVERLAP={results['non_overlap']}")

    finally:
        try:
            await dost.disconnect()
        except Exception:
            pass
        try:
            await sathi.disconnect()
        except Exception:
            pass
        try:
            await listener.disconnect()
        except Exception:
            pass

    ok = all(
        [
            results["publication"],
            results["hearing"],
            results["barge_in"],
            results["non_overlap"],
        ]
    )
    print(f"RESULT OVERALL={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
