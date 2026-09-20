# Sequence Diagrams: RoxStar AI Voice Room Assistant

The following sequence diagrams specify the core workflows and interaction protocols across the human participants, frontend client, backend gateway, LiveKit SFU, agent workers, speech processors, LLM engine, and memory subsystems.

> [!NOTE]
> Diagrams 2 through 5 detail **PLANNED** runtime behaviors for future implementation phases, built upon the Phase 1 protocol foundations.

---

## 1. Human Participant Joins Room

```mermaid
sequenceDiagram
    autonumber
    actor Human as Human User (Rahul / Priya)
    participant UI as Next.js Frontend
    participant Backend as FastAPI Backend (/api/v1)
    participant LiveKit as LiveKit SFU (Planned)
    participant Agent as Agent Worker (Planned)

    Human->>UI: Navigates to /room/demo
    UI->>UI: Mounts RoomShell & initializes static preview state
    Note over UI: Phase 1: Displays static mock cards & "Not connected" badges

    opt Future Phase: Live Connection
        Human->>UI: Clicks "Connect Room"
        UI->>Backend: POST /api/v1/rooms/{id}/token (user identity)
        Backend-->>UI: Returns signed LiveKit JWT Token
        UI->>LiveKit: Connect via WebRTC with JWT
        LiveKit-->>UI: Room Connected & publishes local audio track
        LiveKit->>Agent: Dispatches "participant_joined" event
        Agent->>Agent: Initializes SpeakerProfile in Session Memory
        LiveKit-->>UI: Broadcasts updated participant list (Rahul, Priya, Dost, Sathi)
    end
```

---

## 2. Voice Request & Pipeline Flow (Planned)

```mermaid
sequenceDiagram
    autonumber
    actor Human as Human Speaker
    participant LK as LiveKit Audio Track
    participant STT as Sarvam Saaras STT
    participant TurnMgr as Turn Detector
    participant Router as Bot Router
    participant Memory as Memory Provider
    participant LLM as LLM Engine
    participant TTS as Sarvam Bulbul v3 TTS
    participant Obs as Observability & Telemetry

    Human->>LK: Speaks audio frame ("Dost, weekend pe kya plan hai?")
    LK->>STT: Streams Opus/PCM audio chunks
    STT-->>TurnMgr: Emits interim and final transcripts
    Obs->>Obs: Record STT latency timestamp

    TurnMgr->>TurnMgr: Detects speech completion (Silence boundary > 500ms)
    TurnMgr->>Router: Submits turn payload (speaker="Rahul", text="...")
    
    Router->>Memory: Fetches RoomContext & SpeakerProfile
    Memory-->>Router: Returns context (topic="Weekend", recent turns)
    
    Router->>Router: Evaluates routing rules (User addressed "Dost")
    Router->>LLM: Dispatches prompt tailored for Roxstar AI Dost
    Obs->>Obs: Record LLM invocation timestamp

    LLM-->>Router: Streams completion tokens ("Arre bhai! Kuch badhiya sochte hain...")
    Router->>TTS: Streams text tokens to Sarvam Bulbul v3 (Male voice)
    Obs->>Obs: Record TTFT and TTS first audio chunk latency

    TTS->>LK: Publishes generated audio chunks to Dost's audio track
    LK-->>Human: Human hears Roxstar AI Dost respond in Hindi/Hinglish
    Router->>Memory: Persists completed turn in session context
```

---

## 3. Text Chat Request Flow (Planned)

```mermaid
sequenceDiagram
    autonumber
    actor Human as Human User
    participant UI as Next.js TextChat
    participant LK_Data as LiveKit DataChannel
    participant Router as Bot Router
    participant Memory as Memory Provider
    participant LLM as LLM Engine

    Human->>UI: Types "Sathi, can you summarize the discussion so far?"
    UI->>LK_Data: Sends text message event (speaker, content, timestamp)
    LK_Data-->>UI: Broadcasts chat message to all room participants
    LK_Data->>Router: Dispatches text turn event
    
    Router->>Memory: Retrieves shared voice + text room context
    Memory-->>Router: Returns combined context history
    
    Router->>Router: Identifies direct mention: @Sathi
    Router->>LLM: Requests summary using Roxstar AI Sathi persona
    
    LLM-->>Router: Yields response text
    Router->>LK_Data: Emits bot chat message from AI Sathi
    LK_Data-->>UI: Displays AI Sathi's response in Conversation tab
    Router->>Memory: Appends text response to shared context
```

---

## 4. Bot Routing & Dual-Bot Arbitration (Planned)

```mermaid
sequenceDiagram
    autonumber
    actor Human as Human Speaker
    participant TurnMgr as Turn Detector
    participant Router as Bot Router
    participant TurnLock as Audio Mutex Lock
    participant Dost as Roxstar AI Dost
    participant Sathi as Roxstar AI Sathi

    Human->>TurnMgr: "Rahul, did you finish reviewing the report?"
    TurnMgr->>Router: Submits turn (Human to Human dialogue)

    Router->>Router: Evaluates addressed participant
    Note over Router: Heuristic: Query directed to human participant "Rahul".<br/>Neither bot was summoned.
    
    Router->>Router: Decision = SILENCE (avoid answering every sentence)
    Note over Router: No LLM inference triggered. No audio synthesized.

    Human->>TurnMgr: "Hey guys, what do you think about our launch strategy?"
    TurnMgr->>Router: Submits open-ended query
    Router->>Router: Calculates persona resonance & conversation balance
    
    Router->>TurnLock: Acquire speech mutex lock
    TurnLock-->>Router: Lock acquired for Roxstar AI Sathi
    
    Router->>Sathi: Trigger Sathi response stream
    Note over Dost: Dost suppressed by TurnLock (prevents simultaneous speech)
    
    Sathi-->>Human: Delivers synthesized audio response
    Sathi->>TurnLock: Release speech mutex lock
```

---

## 5. Human Interruption / Barge-In Flow (Planned)

```mermaid
sequenceDiagram
    autonumber
    actor Human as Human Speaker
    participant LK as LiveKit SFU
    participant VAD as Turn Detector / VAD
    participant Router as Bot Router
    participant TTS as Sarvam Bulbul TTS
    participant LLM as LLM Engine

    Note over TTS,LK: AI Dost is actively speaking audio stream to room...
    Human->>LK: Starts speaking: "Wait, Dost, ek second ruko..."
    LK->>VAD: Receives incoming human audio energy
    
    VAD->>Router: Emits BargeInSignal(speaker="Rahul", timestamp)
    
    critical Instant Cancellation
        Router->>TTS: cancel_playback() -> Immediately drop audio output buffer
        TTS->>LK: Clear active audio track queue
        Router->>LLM: cancel_generation() -> Abort in-flight completion stream
    end

    Note over Human,LK: AI audio immediately stops; human speech is heard without collision
    VAD->>Router: Continues buffering human speech as new incoming turn
```
