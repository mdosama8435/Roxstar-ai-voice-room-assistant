# ADR-LLM-002: NVIDIA NIM Controlled Fallback for Primary Gemini Provider

## Status
Accepted

## Date
2026-09-18

## Context
Phase 3C established Google Gemini (`gemini-2.5-flash`) as the real LLM text generation provider for the RoxStar AI Voice Room Assistant. However, cloud LLM providers are susceptible to transient rate limits (HTTP 429), quota exhaustion, intermittent service disruptions (HTTP 503), and network timeouts. In high-concurrency voice room environments, an unhandled provider error results in dropped conversational turns and degraded user experience.

To ensure high availability and resilient conversational flow without altering the core pipeline, an automated secondary provider failover strategy is required.

## Decision
1. **Primary & Secondary Hierarchy**:
   - Google Gemini remains the **PRIMARY** LLM provider.
   - NVIDIA NIM is introduced as a **CONTROLLED FALLBACK** provider for retryable Gemini failures.
   - Default configuration:
     ```bash
     LLM_PRIMARY_PROVIDER=gemini
     LLM_FALLBACK_PROVIDER=nvidia
     LLM_ENABLE_FALLBACK=true
     ```

2. **Common Vendor-Agnostic Abstraction**:
   - Both providers implement the vendor-agnostic `LLMProvider` contract (`generate`, `stream`, `cancel`, `health_check`).
   - The Orchestrator interacts exclusively with `LLMProvider` via `LLMProviderManager`, remaining completely decoupled from concrete vendor SDKs (`google-genai` and `openai`).

3. **Explicit Error Taxonomy & Retryable Classification**:
   - A standardized `ProviderError` categorizes failures into:
     - **Retryable** (eligible for fallback): `rate_limit`, `quota_exhausted`, `service_unavailable`, `connection_failure`, `timeout`.
     - **Non-Retryable** (immediate failure, no fallback): `authentication`, `invalid_model`, `invalid_request`, `cancellation`, `configuration_error`.

4. **Guaranteed Execution Boundaries**:
   - **No Fallback Loops**: Maximum of 2 provider attempts per turn (1 primary + 1 fallback). If NVIDIA also fails, a normalized error is returned.
   - **Context & Persona Preservation**: The identical `LLMRequest` (including system instructions, persona constraints, multi-turn history, and speaker facts) is passed to the fallback provider without requiring the user to repeat queries.
   - **Turn Lock Safety**: The room turn lock is maintained across primary and fallback attempts, and released in a guaranteed `finally` cleanup block under all outcomes.
   - **Single Canonical Response**: Exactly one canonical response message is finalized and published to the LiveKit DataChannel and room context.

5. **Independent Benchmark Mode**:
   - Supports isolated benchmarking (`scripts/benchmark_llm_providers.py`) against Gemini and NVIDIA with identical controlled prompts, recording raw measurements (TTFT, total latency, character length) without ranking or recommendations.

## Consequences

### Positive
- **Fault Resilience**: Room conversations survive temporary Gemini quota exhaustion (HTTP 429) or transient outages by automatically failing over to NVIDIA NIM.
- **Context Continuity**: Multi-user and multi-turn context (e.g., follow-up queries with pronouns) are maintained seamlessly during failover.
- **Security**: All provider API keys remain backend-only, excluded from frontend, git, and logs.
- **Graceful Degradation**: If NVIDIA is configured as fallback but credentials are not yet populated, the system runs normally on Gemini and reports fallback unavailable without crashing.

### Negative / Trade-offs
- Failover requests incur the initial primary timeout/rejection latency before the fallback provider streams tokens.
- Maintaining two provider SDKs (`google-genai` and `openai`) in the backend virtual environment.

## Architecture Diagram
```
                 LLM Request
                      |
                 Gemini Primary
                      |
             ┌────────┴────────┐
             |                 |
          Success          Retryable Error (429/503/timeout)
             |                 |
             ▼                 ▼
          Response          NVIDIA NIM Fallback
                               |
                               ▼
                            Response
```
