# LiveKit Room Integration Guide (Phase 2)

This document specifies the real-time WebRTC audio transport, participant lifecycle, microphone management, and data-channel text chat implemented in **Phase 2** of the RoxStar AI Voice Room Assistant.

---

## 1. Architecture Overview

```
                                    ┌───────────────────────┐
                                    │      LiveKit SFU      │
                                    │ (Cloud / Local Server)│
                                    └───────────┬───────────┘
                                                │
                       ┌────────────────────────┴────────────────────────┐
                 WebRTC Tracks & DataChannel                       WebRTC Tracks & DataChannel
                       │                                                 │
            ┌──────────▼───────────┐                          ┌──────────▼───────────┐
            │  Browser 1: "Rahul"  │                          │  Browser 2: "Priya"  │
            │  (Next.js Client)    │                          │  (Next.js Client)    │
            └──────────┬───────────┘                          └──────────┬───────────┘
                       │ POST /api/v1/livekit/token                      │ POST /api/v1/livekit/token
                       ▼                                                 ▼
            ┌────────────────────────────────────────────────────────────────────────┐
            │                     FastAPI Gateway (/api/v1)                          │
            │          Signs AccessToken with Opaque Identity (human-<uuid>)         │
            └────────────────────────────────────────────────────────────────────────┘
```

Phase 2 replaces the Phase 1 static mock view with a real, multi-party LiveKit WebRTC audio room. All AI pipeline stages (Sarvam Saaras STT, Sarvam Bulbul TTS, LLM conversational reasoning, and semantic routing) remain reserved for **Phase 3**.

---

## 2. Token Generation Flow (`POST /api/v1/livekit/token`)

### Security & Identity Rules
1. **Never Expose Secrets**: `LIVEKIT_API_SECRET` is strictly held on the server and is never transmitted to the client.
2. **Never Put PII into Identities**: Display names (e.g. "Rahul", "Priya") are **never** used as the LiveKit participant identity. The backend generates an opaque, random identity:
   ```text
   identity = "human-" + uuid.uuid4().hex[:12]
   ```
3. **Scoped Grants**: Client tokens are granted minimal necessary permissions:
   - `room_join = true`
   - `room = <requested_room>`
   - `can_publish = true` (audio & data)
   - `can_subscribe = true`
   - `can_publish_data = true`

### Request & Response Contracts

**Request Payload:**
```json
{
  "room_name": "roxstar-test",
  "display_name": "Rahul"
}
```

**Response Payload (HTTP 200):**
```json
{
  "server_url": "wss://your-livekit.livekit.cloud",
  "token": "eyJhbGciOiJIUzI1NiIsIn...",
  "room_name": "roxstar-test",
  "participant_identity": "human-a1b2c3d4e5f6",
  "display_name": "Rahul"
}
```

**Unconfigured Fallback (HTTP 503):**
If `LIVEKIT_URL`, `LIVEKIT_API_KEY`, or `LIVEKIT_API_SECRET` are missing, the server returns HTTP 503 with a clean, actionable error:
```json
{
  "detail": "LiveKit is not configured. Add LiveKit credentials (LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET) to the backend environment."
}
```

---

## 3. Frontend Connection & Hook Architecture (`useLiveKitRoom`)

The client interface connects to LiveKit via the official `livekit-client` SDK encapsulated in `useLiveKitRoom`:

### Supported Lifecycle States
- `IDLE`: Room is not connected. Displays prompt to join.
- `CONNECTING`: Requesting access token and negotiating WebRTC peer connection.
- `CONNECTED`: WebRTC peer connection established, audio tracks and DataChannel active.
- `RECONNECTING`: Temporary network loss; automatic ICE restart in progress.
- `DISCONNECTED`: Clean departure from room; all audio tracks detached.
- `ERROR`: Token failure, network failure, or permission denial.

---

## 4. Audio Transport & Microphone Lifecycle

### Microphone Publishing
- When joining, the client calls `room.localParticipant.setMicrophoneEnabled(true)`.
- If browser microphone permissions are denied, the room remains connected in listen-only mode and logs a warning event without crashing.
- Mute/unmute toggles `localParticipant.setMicrophoneEnabled(false/true)` and broadcasts `RoomEvent.TrackMuted` / `RoomEvent.TrackUnmuted`.

### Remote Audio Subscription
- When a remote participant publishes an audio track, the client catches `RoomEvent.TrackSubscribed`.
- The audio track is attached using `track.attach()` and assigned a unique DOM ID (`audio-${identity}-${sid}`).
- On unmount or `RoomEvent.TrackUnsubscribed`, `track.detach()` cleanly frees audio buffers.
- Prevents duplicate audio elements across re-renders.

### Active Speaker Detection
- LiveKit active speaker events (`RoomEvent.ActiveSpeakersChanged`) update the speaking state of all participants dynamically.
- Speaking indicators only illuminate when acoustic energy is confirmed by the LiveKit SFU.
- **Rule enforced**: `MIC ENABLED != SPEAKING`.

---

## 5. LiveKit DataChannel Text Chat Protocol

Text messaging travels exclusively over the LiveKit reliable DataChannel:

### Message Format (`chat.message`)
```json
{
  "type": "chat.message",
  "message_id": "msg-1742475000000-xyz",
  "sender_id": "human-a1b2c3d4e5f6",
  "sender_name": "Rahul",
  "text": "Hello Priya, can you hear me?",
  "timestamp": "2026-09-17T15:00:00.000Z",
  "version": 1
}
```

Messages are broadcast to all room participants and rendered in the **Text Chat** tab.

---

## 6. Real-time Event Log (`Events` Tab)

All room state transitions are logged with timestamps in the **Events** tab:
- `ROOM_CONNECTING`: Token request dispatched.
- `CONNECTED`: Successfully joined room.
- `PARTICIPANT_JOINED`: Remote participant connected.
- `PARTICIPANT_LEFT`: Remote participant disconnected.
- `AUDIO_SUBSCRIBED`: Subscribed to remote audio stream.
- `TRACK_MUTED` / `TRACK_UNMUTED`: Participant toggled microphone.
- `CHAT_MESSAGE`: Incoming text received over DataChannel.
- `RECONNECTING` / `RECONNECTED`: Network recovery telemetry.

---

## 7. Multi-Browser Testing Procedure

To test a live two-party conversation between **Rahul** and **Priya**:

1. **Configure Environment**:
   Ensure `.env` in the repository root has valid LiveKit credentials:
   ```ini
   LIVEKIT_URL=wss://your-livekit-server.livekit.cloud
   LIVEKIT_API_KEY=your_key
   LIVEKIT_API_SECRET=your_secret
   ```
2. **Start Backend**:
   ```bash
   cd backend
   python -m uvicorn app.main:app --port 8000
   ```
3. **Start Frontend**:
   ```bash
   cd frontend
   npm run dev
   ```
4. **Browser 1 (Rahul)**:
   - Open `http://localhost:3000/room/demo`.
   - Click **Join as: Rahul** (or select Rahul in the modal).
   - Allow microphone permissions.
   - Status badge transitions to `LIVE`, participant count shows `1 participant`.
5. **Browser 2 (Priya)**:
   - Open a private/incognito window to `http://localhost:3000/room/demo`.
   - Click **Join as: Priya**.
   - Allow microphone permissions.
   - Status updates to `2 participants` in both browsers.
6. **Verify Audio & Chat**:
   - Speak into Browser 1's microphone -> verify **Rahul** card displays `Speaking` in both browsers.
   - Type *"Hello Priya"* in Browser 1 -> verify message appears instantly in Browser 2's **Text Chat** tab.
   - Type *"Hi Rahul"* in Browser 2 -> verify message appears in Browser 1.
   - Toggle Mute in Browser 1 -> verify status changes to `Muted` in Browser 2 and event appears in **Events** tab.
   - Click **Leave** in Browser 1 -> Browser 2 immediately records `Rahul left the room` and updates count to `1 participant`.
