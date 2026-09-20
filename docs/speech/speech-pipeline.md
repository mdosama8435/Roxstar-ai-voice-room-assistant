# Speech Processing Pipeline Architecture

This document describes the planned speech recognition (STT) and speech synthesis (TTS) pipeline, powered by Sarvam AI.

---

## 1. Speech-to-Text: Sarvam Saaras
- **Provider Protocol**: `SpeechToTextProvider`
- **Target Endpoint**: Sarvam AI Saaras Streaming API (WebSocket).
- **Audio Input Format**: 16kHz, 16-bit linear PCM, mono channel.
- **Key Capabilities**:
  - Code-mixed Indian English and conversational Hindi transcription.
  - Native Romanized script output for Hinglish utterances.
  - Automatic language detection tag per utterance segment (`hi-IN`, `en-IN`, `hi-Latn`).
- **Resilience & Fallbacks**:
  - Reconnection retry with exponential backoff on WebSocket disconnects.
  - Incomplete utterance buffers flushed if silence exceeds 1,200ms.

---

## 2. Text-to-Speech: Sarvam Bulbul v3
- **Provider Protocol**: `TextToSpeechProvider`
- **Target Endpoint**: Sarvam Bulbul v3 Streaming Audio API.
- **Voice Mappings**:
  - **Roxstar AI Dost**: `sarvam-bulbul-v3-male-hindi` (Friendly, dynamic pace, pitch 1.0, speed 1.05).
  - **Roxstar AI Sathi**: `sarvam-bulbul-v3-female-hindi` (Warm, composed pace, pitch 1.0, speed 1.0).
- **Streaming Pipeline**:
  - LLM token stream is piped into sentence-boundary or clause-boundary buffers.
  - Bulbul generates PCM audio chunks that are sent directly onto the LiveKit WebRTC audio track.
- **Barge-in / Instant Cancellation**:
  - The adapter exposes `cancel_playback()` which resets output buffers and signals the audio track to clear in-flight packets within < 50ms of human interruption.
