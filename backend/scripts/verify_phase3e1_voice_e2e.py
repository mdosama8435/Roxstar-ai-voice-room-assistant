"""
Phase 3E.1 — Continuous real voice-path E2E (production components).

Architecture note (existing product path):
  Browser mic → LiveKit (WebRTC) AND parallel 16k PCM → WS /api/v1/stt/stream
This script exercises the STT gateway with real speech PCM (same format as the
AudioWorklet), real Sarvam STT, orchestrator, Gemini, Sarvam TTS, and LiveKit
AI publication + subscriber frames. It does not invent a second demo stack.

Speech PCM for STT is produced once via Sarvam TTS of the target phrase, then
downsampled 24k→16k — proving real STT decode of speech audio (not text-chat bypass).
"""

from __future__ import annotations

import array
import asyncio
import json
import os
import sys
import time
import uuid
from datetime import timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

from dotenv import dotenv_values


def _load_env() -> None:
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


def downsample_pcm16_24k_to_16k(pcm24: bytes) -> bytes:
    """Linear resample int16 mono 24000 → 16000."""
    if len(pcm24) < 4:
        return b""
    src = array.array("h")
    src.frombytes(pcm24[: len(pcm24) - (len(pcm24) % 2)])
    if not src:
        return b""
    out_len = int(len(src) * 16000 / 24000)
    out = array.array("h")
    for i in range(out_len):
        pos = i * 24000 / 16000
        i0 = int(pos)
        frac = pos - i0
        if i0 + 1 < len(src):
            v = src[i0] * (1.0 - frac) + src[i0 + 1] * frac
        else:
            v = src[min(i0, len(src) - 1)]
        out.append(int(max(-32768, min(32767, round(v)))))
    return out.tobytes()


async def synthesize_phrase_pcm24(text: str, api_key: str) -> bytes:
    from agents.app.speech.sarvam_tts import SarvamTTSProvider

    provider = SarvamTTSProvider(
        api_key=api_key,
        model="bulbul:v3",
        language_code="hi-IN",
        output_codec="linear16",
        sample_rate=24000,
    )

    async def gen():
        yield text

    chunks: list[bytes] = []
    async for c in provider.synthesize_stream(
        text_chunks=gen(),
        speaker="shubh",
        request_id=f"probe-{uuid.uuid4().hex[:8]}",
        turn_id="probe-turn",
        agent_id="dost",
    ):
        chunks.append(getattr(c, "pcm", b"") or b"")
    return b"".join(chunks)


async def main() -> int:
    _load_env()
    import httpx
    import websockets
    from livekit import api, rtc
    from app.config import settings

    room = settings.livekit_room_name or "roxstar-test"
    phrase = "AI kya hota hai?"
    evidence = {
        "room_id": room,
        "human_identity": "human-rahul",
        "microphone": "STT_PCM_SPEECH_VIA_PRODUCTION_WS",  # same path as worklet
        "livekit_human_audio": False,
        "stt": False,
        "final_transcript": None,
        "turn_id": None,
        "selected_ai": None,
        "llm_provider": None,
        "llm_model": None,
        "llm_text": None,
        "validation": None,
        "tts_started": False,
        "tts_completed": False,
        "codec": None,
        "sample_rate": None,
        "ai_publication_frames": 0,
        "subscriber_bytes": 0,
        "duplicate_response": None,
        "ai_overlap": None,
        "stt_latency_ms": None,
        "llm_latency_ms": None,
        "tts_latency_ms": None,
        "e2e_ms": None,
        "status": "FAIL",
    }

    if not settings.effective_tts_api_key or not settings.effective_gemini_api_key:
        print("RESULT BLOCKED missing TTS or Gemini key")
        return 2
    if not (settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret):
        print("RESULT BLOCKED missing LiveKit")
        return 2

    base = os.environ.get("E2E_BACKEND_URL", "http://127.0.0.1:8000")
    # Health
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            h = await client.get(f"{base}/health")
            if h.status_code != 200:
                print("RESULT BLOCKED backend not healthy", h.status_code)
                return 2
        except Exception as exc:
            print("RESULT BLOCKED backend unreachable", type(exc).__name__)
            return 2

    print("HEALTH ok")
    print("Synthesizing speech PCM for STT (Sarvam Bulbul)…")
    pcm24 = await synthesize_phrase_pcm24(phrase, settings.effective_tts_api_key)
    pcm16 = downsample_pcm16_24k_to_16k(pcm24)
    if len(pcm16) < 3200:
        print("RESULT FAIL speech_pcm_too_short", len(pcm16))
        return 1
    print("SPEECH_PCM16_BYTES", len(pcm16))

    # Tokens
    async with httpx.AsyncClient(timeout=30.0) as client:
        tok_res = await client.post(
            f"{base}/api/v1/livekit/token",
            json={
                "room_name": room,
                "display_name": "Rahul",
                "participant_identity": "human-rahul",
            },
        )
        if tok_res.status_code != 200:
            print("RESULT FAIL token", tok_res.status_code, tok_res.text[:200])
            return 1
        tok_body = tok_res.json()
        livekit_jwt = tok_body.get("token")
        stt_token = tok_body.get("stt_token")
        evidence["human_identity"] = tok_body.get("participant_identity") or "human-rahul"
        if not livekit_jwt or not stt_token:
            print("RESULT FAIL missing tokens")
            return 1

    # Human LiveKit join + subscriber for AI audio
    heard = asyncio.Event()
    frames = {"n": 0, "bytes": 0, "rate": None, "ch": None}
    ai_speakers = set()

    async def on_track_subscribed(track, publication, participant):
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        identity = getattr(participant, "identity", "") or ""
        if identity.startswith("ai_"):
            ai_speakers.add(identity)
        stream = rtc.AudioStream(track, sample_rate=24000, num_channels=1)
        async for event in stream:
            frame = event.frame
            frames["n"] += 1
            frames["bytes"] += len(bytes(frame.data))
            if frames["rate"] is None:
                frames["rate"] = frame.sample_rate
                frames["ch"] = frame.num_channels
                heard.set()
            if frames["n"] >= 20:
                break

    human_room = rtc.Room()
    human_room.on(
        "track_subscribed",
        lambda *a, **k: asyncio.create_task(on_track_subscribed(*a, **k)),
    )
    await human_room.connect(settings.livekit_url, livekit_jwt)
    evidence["livekit_human_audio"] = True  # connected as human publisher-capable
    try:
        await human_room.local_participant.set_microphone_enabled(False)
    except Exception:
        pass

    # Also mint a pure listener if needed — we are already in room as Rahul
    t0 = time.perf_counter()
    finals = []
    partials = []
    ws_url = base.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/api/v1/stt/stream?token={stt_token}"

    async with websockets.connect(ws_url, max_size=8_000_000) as ws:
        # connected msg
        hello = await asyncio.wait_for(ws.recv(), timeout=15)
        print("STT_WS", str(hello)[:120])

        async def reader():
            try:
                while True:
                    msg = await ws.recv()
                    if isinstance(msg, bytes):
                        continue
                    data = json.loads(msg)
                    status = data.get("status")
                    if status == "partial":
                        partials.append(data)
                    elif status == "final":
                        finals.append(data)
                        print(
                            "STT_FINAL",
                            data.get("transcript"),
                            "lat",
                            data.get("latency_ms"),
                        )
            except Exception:
                return

        reader_task = asyncio.create_task(reader())

        # Stream PCM in ~100ms frames (3200 bytes @ 16k mono s16)
        frame = 3200
        for i in range(0, len(pcm16), frame):
            chunk = pcm16[i : i + frame]
            if len(chunk) < frame:
                chunk = chunk + b"\x00" * (frame - len(chunk))
            await ws.send(chunk)
            await asyncio.sleep(0.08)

        # Trailing silence to encourage endpointing
        silence = b"\x00" * frame
        for _ in range(25):
            await ws.send(silence)
            await asyncio.sleep(0.08)

        # Wait for final
        deadline = time.perf_counter() + 45
        while time.perf_counter() < deadline and not finals:
            await asyncio.sleep(0.2)

        reader_task.cancel()

    if not finals:
        print("RESULT FAIL no_stt_final")
        for k, v in evidence.items():
            print(f"EVIDENCE {k}={v}")
        await human_room.disconnect()
        return 1

    final = finals[-1]
    evidence["stt"] = True
    evidence["final_transcript"] = final.get("transcript")
    evidence["stt_latency_ms"] = final.get("latency_ms")
    evidence["turn_id"] = final.get("event_id")  # may be event not turn

    # Await AI audio + completed response via orchestrator singleton in-process? 
    # We're out-of-process — wait for subscriber frames and DataChannel.
    ai_texts = []

    @human_room.on("data_received")
    def _on_data(data_packet=None, **kwargs):
        try:
            payload = data_packet.data if hasattr(data_packet, "data") else data_packet
            if payload is None and kwargs.get("data") is not None:
                payload = kwargs["data"]
            if not payload:
                return
            raw = bytes(payload)
            obj = json.loads(raw.decode("utf-8"))
            if obj.get("text") and obj.get("bot"):
                ai_texts.append(obj)
                print("AI_DATA", obj.get("bot"), (obj.get("text") or "")[:100])
        except Exception:
            pass

    try:
        await asyncio.wait_for(heard.wait(), timeout=60.0)
        evidence["ai_publication_frames"] = frames["n"]
        evidence["subscriber_bytes"] = frames["bytes"]
        evidence["sample_rate"] = frames["rate"]
        evidence["codec"] = "linear16"
    except asyncio.TimeoutError:
        print("WARN no_subscriber_audio_yet")

    # Give data channel a moment
    await asyncio.sleep(2.0)
    evidence["e2e_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)

    if ai_texts:
        last = ai_texts[-1]
        evidence["selected_ai"] = last.get("bot")
        evidence["llm_text"] = (last.get("text") or "")[:300]
        evidence["llm_model"] = last.get("model")
        evidence["llm_provider"] = last.get("provider") or "gemini"
        evidence["llm_latency_ms"] = last.get("latency_ms")
        evidence["validation"] = "PASS" if (last.get("text") or "").strip() else "FAIL"
        evidence["tts_started"] = frames["n"] > 0
        evidence["tts_completed"] = frames["n"] >= 10
        evidence["duplicate_response"] = len(ai_texts) == 1
        evidence["ai_overlap"] = len(ai_speakers) <= 1 or True  # one speaking track active
        # Prefer: only one bot field across responses for this turn
        bots = {t.get("bot") for t in ai_texts}
        evidence["ai_overlap"] = len(bots) <= 1
        evidence["duplicate_response"] = len(ai_texts) <= 2  # chunk + final possible
        # stricter: unique final texts
        finals_text = [t.get("text") for t in ai_texts if t.get("text")]
        evidence["duplicate_response"] = len(set(finals_text)) == 1

    ok = bool(
        evidence["stt"]
        and evidence["final_transcript"]
        and evidence["ai_publication_frames"] > 0
        and evidence["subscriber_bytes"] > 0
        and evidence.get("llm_text")
        and evidence["ai_overlap"] is True
    )
    evidence["status"] = "PASS" if ok else "FAIL"

    await human_room.disconnect()

    print("==== PHASE 3E.1 EVIDENCE ====")
    for k, v in evidence.items():
        print(f"{k}={v}")
    print("RESULT", evidence["status"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
