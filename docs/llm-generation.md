# Phase 3C: LLM Response Generation & Persona Intelligence Architecture

## 1. Overview & Pipeline Integration

Phase 3C establishes the real LLM response generation layer for the **RoxStar AI Voice Room Assistant**, completing the pipeline between **Phase 3B Turn Detection & Arbitration** and **Phase 3D Speech Synthesis (TTS)**.

### Pipeline Flow
```
LiveKit Voice / Authenticated Text
               │
               ▼
        TranscriptEvent
               │
               ▼
          TurnDetector
               │
               ▼
       ConversationTurn
               │
               ▼
     Context Update / Snapshot
               │
               ▼
      Response Eligibility
               │
               ▼
      Deterministic Bot Router
               │
               ▼
          Turn Lock
               │
               ▼
 ┌─────────────────────────────┐
 │  Phase 3C: LLM Generation   │
 │                             │
 │ 1. Context Builder          │
 │ 2. Persona Prompt Builder   │
 │ 3. LLMProvider (Gemini/Mock)│
 │ 4. Ephemeral Stream Preview │
 │ 5. OutputValidator          │
 └─────────────┬───────────────┘
               │
               ▼
  LiveKit DataChannel (ai.response)
               │
               ▼
        Release Turn Lock
               │
               ▼
 [Phase 3D: TTS — Future Phase]
```

> **Strict Scope Boundary**: Phase 3C is **TEXT-ONLY**. Zero TTS (Bulbul), zero AI audio tracks published to WebRTC, and zero Gemini Live WebSocket APIs.

---

## 2. LLM Provider Architecture

### 2.1 Vendor-Agnostic Interface (`backend/app/services/llm/base.py`)
The orchestrator interacts exclusively with the abstract `LLMProvider` contract:
```python
class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse: ...

    @abstractmethod
    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]: ...

    @abstractmethod
    async def cancel(self, request_id: str) -> None: ...

    @abstractmethod
    async def health_check(self) -> bool: ...
```

### 2.2 Isolated Google Gemini Provider (`backend/app/services/llm/gemini_provider.py`)
- Utilizes the **official Google Gen AI SDK** (`google-genai`), avoiding deprecated `google-generativeai`.
- Direct SDK usage isolated to `gemini_provider.py`; never imported directly by orchestrator or frontend.
- Uses `client.aio.models.generate_content_stream(model=..., contents=..., config=...)`.
- Configuration:
  - `LLM_PROVIDER=gemini`
  - `LLM_MODEL=gemini-2.5-flash`
  - `LLM_TEMPERATURE=0.7`
  - `LLM_MAX_OUTPUT_TOKENS=300`
  - `LLM_TIMEOUT_SECONDS=15.0`

### 2.3 Deterministic Mock Provider (`backend/app/services/llm/mock_provider.py`)
- Fast, deterministic responses for CI and automated test suites.
- Heuristic intent matching with natural conversational Hindi/Hinglish fallbacks.
- Yields to the asyncio event loop (`await asyncio.sleep(0.001)`) to ensure cooperative cancellation tasks and stream interruptions can run without deadlock.
- Supports fault injection flags: `simulate_timeout`, `simulate_rate_limit`, `simulate_failure`, and `simulate_empty`.

### 2.4 Provider Factory & Fallback (`backend/app/services/llm/factory.py`)
- When `GEMINI_API_KEY` is not present (standard local dev / CI), automatically uses `MockLLMProvider` without crashing or failing tests.
- When `GEMINI_API_KEY` is set, instantiates `GeminiLLMProvider`.

---

## 3. Persona Intelligence & Prompt Engineering

### 3.1 Personas
- **AI Dost (`backend/app/services/personas/dost.py`)**:
  - Male, energetic, direct, casual brother/friend vibe (*bhai* / *dost*).
  - Uses modern conversational Hindi/Hinglish with everyday tech comfort.
  - Keeps answers concise (1–3 sentences), spoken-first, avoiding bullets.
- **AI Sathi (`backend/app/services/personas/sathi.py`)**:
  - Female, warm, empathetic, patient guide and thoughtful conversational partner.
  - Explains concepts gently with clear relatable analogies.
  - Natural spoken cadence (1–3 sentences).

### 3.2 Structured Prompt Construction (`backend/app/services/personas/prompt_builder.py`)
Assembled into structured tiers:
1. **Persona Base Instructions**: Voice identity, tone, and behavioral profile.
2. **Language & Natural Cadence**: Natural conversational Hindi/Hinglish, phonetically clear for future voice conversion.
3. **Spoken Output Constraints**: No markdown headers, asterisks, bullet points, numbered lists, tables, raw URLs, or emojis.
4. **Safety & Anti-Injection Guardrails**: Strict isolation against prompt injection, jailbreaking, instruction overrides, or identity impersonation.
5. **Context History & Speaker Isolation**: Multi-turn history, active topic, and extracted facts for the active speaker only (preventing cross-participant fact leakage).
6. **Triggering User Utterance**: Sanitized human input.

---

## 4. Streaming, Validation & Anti-Race Cancellation

### 4.1 Ephemeral Preview vs. Canonical Response
- **Stream Chunks (`ai.response.chunk`)**: Broadcast to the LiveKit DataChannel ephemeral topic. Frontend displays a temporary streaming preview card with typing dots without creating persistent chat messages.
- **Output Validation**: Once the complete stream is accumulated, `OutputValidator.validate(raw_text)` runs:
  - Strips markdown formatting (`#`, `**`, `*`, ```` ``` ````, `|`).
  - Removes raw URLs and web links.
  - Enforces word limit (max 80 words) and cleanly truncates at the nearest sentence boundary (`.`, `!`, `?`, `|`, `\n`).
  - Rejects empty or whitespace-only outputs.
- **Canonical Response (`ai.response`)**: Exactly ONE permanent `ai.response` message is broadcast, recorded in room context, and appended to the chat timeline.

### 4.2 Anti-Race Cancellation Semantics
1. Orchestrator records `request_id` in `self._cancelled_requests` and invokes `provider.cancel(request_id)`.
2. Provider halts chunk consumption loop.
3. Post-stream check verifies: `if llm_request.request_id in self._cancelled_requests: return None`.
4. Even if cancellation arrives immediately before or on the final chunk, **publication of `ai.response` is completely suppressed**.
5. `finally:` block guarantees the turn lock is released on the room mutex:
```python
finally:
    if acquired_lock:
        await turn_lock_manager.release(turn.room_id, selected_bot, turn.turn_id)
    self._in_flight_turns.discard(turn.turn_id)
```

---

## 5. Automated Testing & Verification

### Test Suite (`backend/tests/test_llm.py`)
- Total tests: 21 (20 passed, 1 opt-in skipped).
- Covers:
  - Mock provider streaming, cancellation, and simulated errors.
  - Gemini provider structure and missing key health-check guards.
  - Persona system prompts and anti-injection instructions.
  - OutputValidator markdown removal, sentence boundary truncation, and empty rejection.
  - Conversation context builder speaker isolation and bounded FIFO turn window.
  - Orchestrator generation, idempotency, and race-free cancellation.
  - **Assignment Scenarios 1–5**:
    1. *Rahul: "AI kya hota hai?"* -> Natural conversational Hindi/Hinglish response.
    2. *Rahul: "What is cloud computing?"* -> Understood in English, answered in Hinglish.
    3. *Rahul: "Unki koi famous movie?"* -> Pronoun resolution from prior SRK context.
    4. *Priya: "Thoda aur simple batao."* -> Multi-user follow-up using shared room dialogue.
    5. *Rahul: "Maine tumhe kya bataya tha?"* -> Memory retrieval from speaker profile facts.
- **Opt-in Live Gemini Smoke Test**:
  - `test_real_gemini_live_smoke_test` is decorated with `@pytest.mark.skipif(os.getenv("RUN_LLM_LIVE_TEST") != "true" or not settings.effective_gemini_api_key, ...)`
  - Runs against live Google Gemini API only when explicitly invoked:
    ```bash
    $env:RUN_LLM_LIVE_TEST="true"
    $env:GEMINI_API_KEY="AIzaSy..."
    pytest backend/tests/test_llm.py -k test_real_gemini_live_smoke_test
    ```

### Full Repository Regression Status
- Total tests: **68 tests** (67 passed, 1 skipped).
- **All 47 previous tests from Phase 1, Phase 2, Phase 3A, and Phase 3B preserved with 100% pass rate**.
