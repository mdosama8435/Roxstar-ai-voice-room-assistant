# ADR 001: Abstract Interfaces for External AI Providers

## Status
Accepted

## Context
The RoxStar AI Voice Room Assistant requires integration with multiple external AI providers:
- Speech-to-Text (STT): Sarvam Saaras streaming interface.
- Text-to-Speech (TTS): Sarvam Bulbul v3 streaming interface.
- Large Language Models (LLM): Provider agnostic (OpenAI, Anthropic, Sarvam, etc.).

Directly embedding vendor-specific SDK calls across the agent logic violates modularity, prevents isolated unit testing, and makes provider switching costly.

## Decision
All external AI services must be isolated behind Python `typing.Protocol` interfaces:
- `SpeechToTextProvider`: Ingests audio stream chunks and emits transcript events.
- `TextToSpeechProvider`: Consumes text streams and emits synthesized audio frames with cancellation support.
- `LanguageModelProvider`: Accepts conversational turns and produces streaming text tokens.

Concrete adapter classes (e.g. `SarvamSaarasSTTAdapter`, `SarvamBulbulTTSAdapter`) will implement these protocols. Core orchestration logic will interact exclusively with the abstract protocols.

## Consequences
- **Positive**: Unit testing without network calls or API keys; seamless mock injection; zero provider lock-in.
- **Negative**: Requires maintaining explicit adapter classes and serializable intermediate data models.
