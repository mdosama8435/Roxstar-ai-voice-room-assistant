# System Architecture: RoxStar AI Voice Room Assistant

## 1. Product Goal
The **RoxStar AI Voice Room Assistant** is an intelligent, multi-user, real-time voice and text room platform. Human participants engage in natural voice and text interactions with two distinct AI personas:
- **Roxstar AI Dost**: A friendly, relatable, male Hindi/Hinglish persona who speaks with conversational warmth.
- **Roxstar AI Sathi**: An empathetic, supportive, female Hindi/Hinglish persona offering distinct perspectives.

Key interaction requirements:
- Multilingual conversational understanding across Hindi, Roman Hinglish, and English.
- Natural speech synthesis in authentic Indian conversational tones.
- Shared voice and text context: conversations started in text or voice inform the unified room context.
- Multi-speaker awareness: tracking speaker turns, attributing facts, and remembering user preferences.
- Barge-in / interruption support: human speech instantly halts ongoing AI speech synthesis.
- Intelligent bot routing: prevents both bots from talking at the same time or chiming in after every human sentence.

---

## 2. Current Phase 1 Architecture vs. Target Architecture

```
[ PHASE 1: FOUNDATION & CONTRACTS ]                [ TARGET ARCHITECTURE: FULL RUNTIME ]
+------------------------------------+             +------------------------------------+
|  Next.js Dark Shell (Mock State)   |             |  Next.js + LiveKit WebRTC Client   |
|  - Static participant cards        |             |  - Real-time WebRTC audio tracks   |
|  - Offline indicators              |             |  - Live wave visualizers & tokens  |
+-----------------+------------------+             +-----------------+------------------+
                  |                                                  | WebRTC / DataChannel
+-----------------v------------------+             +-----------------v------------------+
|  FastAPI Backend Foundation        |             |  LiveKit Cloud / Server SFU        |
|  - /health & /system/status        |             |  - Room token generation           |
|  - Pydantic v2 data contracts      |             |  - Audio forwarding & track events |
+-----------------+------------------+             +-----------------+------------------+
                  |                                                  | WebRTC Agent Worker
+-----------------v------------------+             +-----------------v------------------+
|  Agent Foundation (Protocols)      |             |  LiveKit Agent Orchestrator        |
|  - STT/TTS/LLM abstract protocols  |             |  - Sarvam Saaras STT Streaming     |
|  - Dost / Sathi persona configs    |             |  - Turn Detector & Barge-in Mgr    |
|  - Router & Memory protocols       |             |  - Bot Router (Dost/Sathi/Silence) |
|  - Structured logging utilities    |             |  - LLM Reasoning & Memory Engine   |
+------------------------------------+             |  - Sarvam Bulbul v3 TTS Streaming  |
                                                   +------------------------------------+
```

### Distinction Table

| Subsystem | IMPLEMENTED NOW (Phase 1 & Phase 2) | PLANNED FOR PHASE 3 |
| :--- | :--- | :--- |
| **Frontend LiveKit Client** | Real `livekit-client` WebRTC audio subscription, microphone publishing, active speaker events, real-time DataChannel text chat, live lifecycle event log, dynamic participants (Rahul & Priya) | Real-time speech transcription UI stream, dual-persona voice visualizers, barge-in wave sync |
| **Backend API Gateway** | FastAPI application, `/health`, `/api/v1/system/status`, `POST /api/v1/livekit/token` (opaque identities, scoped grants), Pydantic contracts, structured JSON logging | LiveKit room webhook ingestion, participant analytics, persistent session storage |
| **Agent Layer** | Python abstract protocols (`SpeechToTextProvider`, `TextToSpeechProvider`, `LanguageModelProvider`, `MemoryProvider`, `BotRouter`), Persona configurations | LiveKit Agents worker runtime, WebRTC audio track pipelines for Dost and Sathi |
| **Speech Processing** | Sarvam Saaras & Bulbul interface specifications and configuration schemas | Real-time WebSocket streaming to Sarvam API endpoints, audio chunking, TTS audio playback |
| **LLM & Reasoning** | Provider abstraction protocol and system prompts for Dost and Sathi | Live streaming LLM client (OpenAI/Anthropic/Groq/Sarvam) with function calling |
| **Memory Engine** | MemoryProvider protocol, session state interface, speaker fact schema | Redis session store for ephemeral turns, PostgreSQL + pgvector for semantic recall |
| **Turn & Routing** | Router protocol, `AgentDecision` schema with `SILENCE` option, turn lock protocol | Real-time VAD, end-of-turn classification, barge-in audio cut-off, arbitration heuristics |
| **Observability** | Context-bound structured JSON logger, latency metric contracts, error models | OpenTelemetry metrics, Prometheus exporter, end-to-end audio latency tracking |

---

## 3. Frontend Architecture
- **Framework**: Next.js (App Router), React 19 / 18, TypeScript (Strict).
- **Styling**: Tailwind CSS with custom glassmorphism utilities, dark obsidian palette (`#090a0f`), violet/pink accent glows.
- **Component Hierarchy**:
  - `RoomShell`: Top-level flex container coordinating layout.
  - `Sidebar`: Navigation, brand identity ("Let it be heard."), and tool drawers.
  - `Topbar`: Room metadata chips (Room ID, Connection status, Participant count, Latency indicator).
  - `ParticipantGrid` / `ParticipantCard`: 4 cards representing human participants (Rahul, Priya) and AI participants (AI Dost, AI Sathi). Includes status badges (Speaking, Listening, Muted, Connecting, Disconnected, AI thinking).
  - `ConversationPanel` & `TextChat`: Tabbed view for conversation transcripts, text messaging, room events, and latency analytics.
  - `IntelligencePanel`:
    - `RoomContextCard`: Displays current topic, active speaker, agent in focus, and language style.
    - `SpeakerMemoryCard`: Displays stored participant facts.
    - `BotRoutingCard`: Displays arbitration decision and bot selection rationale.
    - `PipelineCard`: Step-by-step pipeline view (*LiveKit → STT → Turn → Router → Memory → LLM → TTS*).
  - `RoomControls`: Mute, Start Speaking, Share, Leave Room buttons (clearly marked unavailable in Phase 1).

---

## 4. Backend Architecture
- **Framework**: FastAPI with Uvicorn worker.
- **Configuration**: Pydantic BaseSettings (`app/config.py`) loading from `.env` or system environment. Does not crash if optional provider keys are absent during startup.
- **Endpoints**:
  - `GET /health`: Basic liveness probe returning `{"status": "ok", "service": "roxstar-backend"}`.
  - `GET /api/v1/system/status`: Real system status inspects environment, Python version, runtime health, and provider configuration flags without exposing secret values.
- **Schema Contracts** (`app/schemas/contracts.py`):
  - `Participant`: User or agent participant identity, role, and media state.
  - `Room`: Room identifier, lifecycle state, active participants, and configuration.
  - `TranscriptEvent`: Single speech or text utterance with language tag and confidence.
  - `ConversationTurn`: Aggregated conversational turn containing speaker, text, and timing.
  - `AgentDecision`: Arbitration output containing selected bot (Dost, Sathi, or Silence), reasoning, and confidence.
  - `SpeakerProfile`: Multi-user profile storing name, language preference, and remembered facts.
  - `RoomContext`: Shared room context linking topic, active speaker, and recent turns.
  - `PipelineEvent`: Lifecycle event tracking each stage of processing.
  - `LatencyMetric`: Detailed latency breakdown across STT, LLM TTFT, TTS playback, and E2E.

---

## 5. LiveKit Integration Strategy (Planned)
- **Transport Protocol**: WebRTC with Selective Forwarding Unit (SFU) architecture.
- **Agent Participation**: LiveKit Agents Python worker connects directly as a room participant with dedicated audio tracks for Dost and Sathi.
- **Data Channel**: Custom JSON messages for room state synchronization, transcript broadcasting, and pipeline status telemetry.

---

## 6. Agent Layer Architecture
- **Modular Decoupling**: Agent workers run independently of the HTTP backend.
- **Persona Architecture**:
  - `Roxstar AI Dost`: Energetic, friendly brotherly tone ("bhai", "yaar"), quick with practical advice, relatable humor.
  - `Roxstar AI Sathi`: Empathetic, composed, articulate female persona, excels at thoughtful synthesis and emotional nuance.
- **System Prompts**: Enforce natural Indian conversational phrasing, code-mixing rules (Hindi-English without sounding forced), and adherence to persona boundaries.

---

## 7. Speech Layer (Planned Provider: Sarvam AI)
- **STT Interface**: `SpeechToTextProvider` protocol. Designed for Sarvam Saaras streaming API, accepting raw audio PCM buffers and returning incremental and final transcripts with language identification (`hi`, `en`, `hi-Latn`).
- **TTS Interface**: `TextToSpeechProvider` protocol. Designed for Sarvam Bulbul v3 streaming API, accepting text strings and yielding audio chunks for immediate WebRTC track playback.
- **Barge-in / Cancellation**: TTS playback must support instantaneous `cancel_playback()` signals upon voice activity detection.

---

## 8. LLM Layer & Orchestration
- **Abstraction**: `LanguageModelProvider` protocol supports streaming completions, prompt injection, and structured outputs.
- **Provider Agnostic**: Configurable to connect to OpenAI, Anthropic, Sarvam, or local models.
- **Temperature & Style Control**: Fine-tuned per persona for conversational agility.

---

## 9. Memory & Context Management
- **Short-Term Session Memory**: Ephemeral sliding-window conversation turns maintained in Redis or in-process cache.
- **Speaker Profiling**: Associating facts, preferences, and linguistic style to specific participant IDs.
- **Long-Term Semantic Memory**: (Planned) PostgreSQL with `pgvector` for cross-session knowledge retrieval.
- **Context Summarization**: Automatic truncation and rolling summarization when context windows exceed threshold tokens.

---

## 10. Bot Routing & Arbitration
- **Problem**: In a room with two AI agents and two humans, multiple agents must not speak over each other, nor should an AI respond to every human utterance.
- **Arbitration Strategy**:
  1. **Addressed Directly**: If user specifies "Dost" or "Sathi", route directly to the requested persona.
  2. **Topical Resonance**: If topic fits Dost's practical tone or Sathi's empathetic tone, assign highest affinity score.
  3. **Turn Alternation**: Balance participation between bots so one does not dominate.
  4. **Silence / Non-Interference**: If humans are talking to each other without inquiring of the bots, router selects `SILENCE`.
  5. **Turn Lock**: A distributed or local mutex guarantees only one audio stream plays at any given instant.

---

## 11. Observability & Telemetry
- **Structured JSON Logs**: Every log entry includes `timestamp`, `log_level`, `request_id`, `room_id`, `participant_id`, and `event_type`.
- **Metrics Breakdown**:
  - STT First Chunk Latency
  - LLM Time to First Token (TTFT)
  - TTS Audio Generation Latency
  - Total Voice-to-Voice Latency (End-to-End)
- **Sanitization**: Automatic scrubbing of authorization tokens, passwords, and raw audio payloads.

---

## 12. Security
- **Authentication**: LiveKit JWT token generation with scoped permissions (publish, subscribe, room identity).
- **Environment Isolation**: No secrets committed to source control; zero hardcoded fallback credentials.
- **Input Validation**: Strict Pydantic validation on all ingress payloads.

---

## 13. Privacy & Audio Handling
- **No Raw Audio Storage by Default**: Audio buffers are processed purely in ephemeral RAM and discarded immediately following transcription.
- **Data Minimization**: Loggers record message metadata and token counts, never raw audio waveforms or private personal identifiable information (PII).

---

## 14. Cost Considerations & Economics
- **STT Optimization**: Voice Activity Detection (VAD) ensures audio is streamed to STT only when speech is present, reducing unnecessary Sarvam API streaming minutes.
- **Selective TTS**: Bot routing prevents dual synthesis; only the chosen persona generates speech.
- **Prompt Token Optimization**: Context truncation and semantic memory pruning minimize prompt token expansion during long conversations.
