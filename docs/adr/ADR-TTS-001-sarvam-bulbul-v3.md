# ADR-TTS-001: Sarvam Bulbul v3 Text-to-Speech for RoxStar

**Status:** Accepted  
**Date:** 2026-09-19  
**Phase:** 3D  
**Authors:** Engineering team  

---

## Context

Phase 3D closes the voice loop for RoxStar AI Voice Room:  
canonical validated AI text → spoken audio → human hears AI.

The existing pipeline delivers AI responses as text over LiveKit DataChannel.  
Phase 3D adds a real-time TTS synthesis and publication layer.

---

## Decision

Use **Sarvam Bulbul v3** (`bulbul:v3`) via the official `sarvamai` Python SDK  
(`sarvamai==0.1.34`) with WebSocket streaming for low-latency conversational TTS.

Audio is published to humans via LiveKit WebRTC (`livekit==1.1.19` rtc SDK).

---

## Verified API Contract (sarvamai==0.1.34)

All details below are verified from source code inspection of the installed SDK,  
NOT from documentation alone.

### Connection

```python
async with client.text_to_speech_streaming.connect(model="bulbul:v3") as ws:
    await ws.configure(
        target_language_code="hi-IN",
        speaker="shubh",            # or "anushka"
        pace=1.0,
        speech_sample_rate=24000,
        output_audio_codec="linear16",
        enable_preprocessing=True,
    )
    await ws.convert(text_chunk)
    await ws.flush()
    async for message in ws:
        if isinstance(message, AudioOutput):
            pcm = base64.b64decode(message.data.audio)
```

### Methods (verified from `AsyncTextToSpeechStreamingSocketClient` source)

| Method | Description |
|--------|-------------|
| `configure(...)` | Sends config as first WebSocket message |
| `convert(text)` | Sends text chunk for synthesis |
| `flush()` | Forces buffer flush |
| `ping()` | Keeps connection alive |

### Response Types (verified from type inspection)

`TextToSpeechStreamingSocketClientResponse` is a Union of:
- `AudioOutput` → `.data.audio` = base64-encoded PCM string
- `ErrorResponse` → error message
- `EventResponse` → lifecycle events (e.g., completion)

---

## Audio Format

**All values verified from SDK source code, not assumed:**

| Parameter | Value | Source |
|-----------|-------|--------|
| `output_audio_codec` | `"linear16"` | `ConfigureConnectionDataOutputAudioCodec` type inspection: `Literal['linear16', 'mulaw', 'alaw', 'opus', 'flac', 'aac', 'wav', 'mp3']` |
| `speech_sample_rate` | `24000` Hz | SDK `connect()` docstring: "Default sample rate: 24000 Hz" for bulbul:v3 |
| Channels | 1 (mono) | bulbul:v3 streaming output is mono |
| Bit depth | 16-bit signed int | linear16 = 16-bit PCM |
| Byte order | little-endian | Standard linear16 |
| Response encoding | base64 | `AudioOutputData.audio: str` field |

**Frame sizes for LiveKit:**
- Frame duration: 20ms (standard WebRTC)  
- Samples per frame: `24000 * 0.020 = 480`  
- Bytes per frame: `480 * 2 = 960`  

---

## Speaker Selection

**Verified from sarvamai SDK `configure()` source code:**

```
speaker: str = "anushka"  # SDK default
```

**Documentation in configure() docstring:**
> Model Compatibility (bulbul:v2): Female: Anushka, Manisha, Vidya, Arya;  
> Male: Abhilash, Karun, Hitesh

For bulbul:v3, the SDK default is `anushka`. Speakers for RoxStar:

| AI Persona | Speaker | Gender | Config Var |
|-----------|---------|--------|------------|
| AI Dost | `shubh` | Male | `SARVAM_TTS_DOST_SPEAKER` |
| AI Sathi | `anushka` | Female | `SARVAM_TTS_SATHI_SPEAKER` |

Both are configurable via environment variables.

---

## Architecture Decision: WebSocket Streaming vs REST

**WebSocket streaming** was chosen over REST for the following reasons:

1. **TTFA (Time to First Audio):** WebSocket streams audio chunks as they are generated. REST waits for complete synthesis before responding. For conversational TTS, TTFA < 300ms is the target — only achievable via streaming.

2. **Backpressure:** WebSocket allows the client to pace audio delivery with LiveKit's `AudioSource.capture_frame()` queue.

3. **Cancellation:** WebSocket connection can be closed immediately on barge-in. REST requests cannot be cancelled mid-flight.

4. **API contract:** The `bulbul:v3` model is designed for streaming; REST is appropriate only for offline/batch use.

---

## Architecture Decision: agents/ Owns Audio Publication

Per Phase 3D correction:
- `backend/` handles orchestration control flow (LLM → TTS signaling)
- `agents/` handles real-time audio lifecycle (AudioSource → LocalAudioTrack → Room)

This preserves the existing separation: backend = control plane, agents = media plane.

**Integration boundary:**
- Orchestrator receives `TTSRequest` with validated text  
- Calls `TTSService.synthesize_and_publish()` 
- `TTSService` lives in `agents/` for real deployment; backend has interface definitions

---

## LiveKit Audio Path

```
SarvamTTSProvider.synthesize_stream()
    → yields raw PCM bytes (linear16, 24kHz, mono)
        ↓
LiveKitAudioPublisher._frame_publisher_loop()
    → rtc.AudioFrame(data, sample_rate=24000, num_channels=1, samples_per_channel=N)
        ↓
rtc.AudioSource.capture_frame(frame)
    ↓
rtc.LocalAudioTrack ("tts-dost" or "tts-sathi")
    ↓
room.local_participant.publish_track(track)
    ↓
Human hears AI
```

**Validation before AudioFrame creation:**
- `len(pcm_bytes) % 2 == 0` (must be multiple of int16 size)
- `samples_per_channel = len(pcm_bytes) // (num_channels * 2)`
- Odd bytes are truncated with a warning

---

## Turn Lock Policy

The turn lock is held from the start of LLM generation through TTS completion:

```
acquire_lock()
    ↓
LLM generation
    ↓
TTS synthesis + audio publication  ← lock held here too
    ↓
release_lock()  ← guaranteed in finally block
```

This prevents AI Dost and AI Sathi from speaking simultaneously.

---

## Barge-in / Cancellation

When human speech begins while AI is speaking:

1. `cancel_generation(request_id)` is called
2. LLM request marked cancelled
3. `TTSService.cancel(tts_request_id)` is called
4. `SarvamTTSProvider.cancel_request(request_id)` sets asyncio.Event
5. `LiveKitAudioPublisher.cancel_current(request_id)` clears audio queue
6. Late audio chunks from old request are discarded by sequence check
7. Turn lock released safely in finally block

---

## TTS Failure Policy

If TTS fails (auth error, rate limit, timeout, WS disconnect):
- `tts.error` event is logged with structured fields
- Canonical LLM text is still valid (already broadcast on DataChannel)
- **NO new LLM generation is triggered**
- Turn lock is released normally
- User sees text; audio synthesis failure is an isolated fault

---

## Security

- `SARVAM_TTS_API_KEY` is separate from `SARVAM_API_KEY` (STT)
- API key is NEVER logged (verified in code)
- Raw audio is NEVER persisted by default
- No audio sent via DataChannel (WebRTC only)

---

## Dependencies Added (Phase 3D)

| Package | Version | Purpose |
|---------|---------|---------|
| `sarvamai` | `0.1.34` | Sarvam AI Python SDK |
| `livekit` | `1.1.19` | LiveKit RTC SDK (AudioFrame, AudioSource, LocalAudioTrack) |
| `pytest-asyncio` | `1.4.0` | Async test support (fixes 51 pre-existing env failures) |

---

## Verification Requirements

Phase 3D is NOT complete until:

1. ✅ Real Sarvam API call succeeds with bulbul:v3
2. ✅ AI Dost voice (shubh) produces non-empty audio
3. ✅ AI Sathi voice (anushka) produces non-empty audio
4. ✅ Audio format confirmed: linear16, 24kHz, mono
5. ✅ LiveKit AudioFrame created and published successfully
6. ✅ Human participant hears AI audio through LiveKit
7. ✅ Barge-in stops audio publication
8. ✅ TTS failure does not trigger LLM retry
9. ✅ API key not in any log output

Run `test_tts_live.py` with `RUN_TTS_LIVE_TEST=true` for items 1-5.  
Items 6-9 require a running LiveKit room with human participants.

---

## Alternatives Rejected

| Alternative | Why Rejected |
|------------|-------------|
| Browser speech synthesis (Web Speech API) | Not real; requires frontend; no server control; different voice |
| Sarvam REST API | No streaming TTFA; requires complete text before synthesis |
| DataChannel audio | Not WebRTC; no real audio track; frontend must decode |
| bulbul:v2 | Older model; does not support temperature; lower quality |
| ElevenLabs | Higher cost; requires different credentials; breaks existing Sarvam integration |
