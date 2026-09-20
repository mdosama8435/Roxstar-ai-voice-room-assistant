# Engineering Rules & Architectural Principles

These 30 engineering rules represent non-negotiable standards for developing the **RoxStar AI Voice Room Assistant**. Every component, service, and PR must strictly comply with these principles.

---

### Core Principles

1. **Type safety is mandatory.**  
   All codebases must enforce strict type systems. No untyped or loosely typed boundary layers are allowed.

2. **Python code must use type hints.**  
   All Python functions, methods, parameters, and return values must be explicitly typed using standard library `typing` or modern Python 3.10+ syntax (`|`, `list[str]`, etc.).

3. **Pydantic models must be used for API contracts.**  
   All input payloads, outbound responses, events, and inter-service state representations must be strongly typed with Pydantic v2 schemas.

4. **TypeScript strict mode must be enabled.**  
   The frontend `tsconfig.json` must enforce `"strict": true`, `"noImplicitAny": true`, and strict null checking.

5. **Never commit secrets.**  
   Never commit `.env` files, API keys, private keys, LiveKit secrets, or credentials to version control.

6. **Never hardcode API keys.**  
   All keys, tokens, endpoints, and credentials must be injected dynamically at runtime via environment variables or secret managers.

7. **All configuration must come from environment variables.**  
   Services must read configuration through declarative settings models (such as `pydantic_settings.BaseSettings`) with environment variable backing.

8. **External provider integrations must be isolated behind interfaces/adapters.**  
   Code must depend on abstract protocols (`SpeechToTextProvider`, `TextToSpeechProvider`, `LanguageModelProvider`), never directly on vendor SDKs in core business logic.

9. **LiveKit transport logic must remain separate from business logic.**  
   WebRTC transport, room subscription, and audio track handling must be abstracted away from voice agent reasoning and dialog state management.

10. **Agent routing must remain separate from LLM provider implementation.**  
    Determining which bot responds (Roxstar AI Dost vs. Roxstar AI Sathi vs. silence) must be an isolated arbitration engine independent of the underlying LLM vendor.

11. **Memory must remain separate from agent persona logic.**  
    Ephemerality, persistence, vector retrieval, and context truncation must be modularized into dedicated memory services rather than coupled to agent prompts.

12. **Provider failures must never crash the entire room.**  
    If STT, TTS, or LLM services fail or timeout, the room connection must remain healthy, and graceful fallbacks or status updates must be communicated.

13. **Important operations must have structured logging.**  
    All critical lifecycle events must be emitted as structured JSON containing contextual metadata (`request_id`, `room_id`, `participant_id`, `event_type`, `timestamp`).

14. **Do not log API keys, tokens, raw secrets, or sensitive audio.**  
    Loggers must redact authentication headers, tokens, credentials, and never write raw audio payloads or PII into logs.

15. **Do not store raw room audio by default.**  
    Audio streams are ephemeral and processed in-memory for real-time inference. No raw WAV/PCM files are written to disk unless an explicit recording session is consented to by users.

16. **Prefer deterministic logic when deterministic logic is sufficient.**  
    Use rule-based state machines, keyword triggers, and heuristic filters before delegating simple decisions to costly and non-deterministic LLM calls.

17. **Use an LLM only when semantic reasoning is actually required.**  
    Do not waste latency and tokens invoking LLMs for fixed routing, simple command dispatch, or deterministic turn detection.

18. **Every major feature must have tests.**  
    No feature is complete without accompanying unit and integration tests.

19. **Do not create fake production behavior merely to satisfy a demo.**  
    Do not simulate fake AI audio responses, fake transcripts, fake latency metrics, or mocked provider states that disguise missing implementation.

20. **Do not introduce dependencies without a reason.**  
    Keep the dependency tree lean, audited, and purposeful. Evaluate whether standard libraries or lightweight primitives suffice before adding third-party packages.

21. **Avoid unnecessary abstractions.**  
    Write clean, readable, modular code. Do not introduce speculative design patterns or multi-layered indirection until concrete requirements demand them.

22. **Avoid giant files.**  
    Keep files focused, cohesive, and concise. Decompose large controllers or UI pages into single-responsibility submodules.

23. **Keep modules focused on one responsibility.**  
    Follow Single Responsibility Principle (SRP). A module handles transport, parsing, arbitration, or persistence—not all four.

24. **Do not modify unrelated files.**  
    When fixing a bug or adding a feature, restrict file edits strictly to the relevant scope to prevent regression risks.

25. **Before implementing a feature, inspect the existing architecture.**  
    Verify established patterns, shared schemas, and interfaces before authoring new components.

26. **Maintain backwards compatibility with already implemented functionality.**  
    Do not break existing API contracts, schema models, or component interfaces without a documented migration path.

27. **Never silently swallow exceptions.**  
    Always catch specific exception types, log them with contextual tags, and handle them or bubble them up appropriately. Avoid blank `except: pass`.

28. **All external calls must eventually have timeout and failure handling.**  
    All HTTP requests, WebSocket calls, streaming RPCs, and database connections must enforce bounded timeouts and exponential backoff retry strategies.

29. **Design for interruption and cancellation from the beginning.**  
    Real-time voice demands immediate cancellation of ongoing TTS playback and LLM generation when human speech (barge-in) is detected.

30. **Design for multi-user concurrency.**  
    The architecture must cleanly support multiple human participants concurrently talking, sending text, or disconnecting without state corruption or race conditions.
