# ADR 003: Dual Persona Arbitration and Speech Mutex

## Status
Accepted

## Context
RoxStar AI Voice Room hosts two distinct AI personas in the same room:
- **Roxstar AI Dost** (Male, friendly Hindi/Hinglish persona)
- **Roxstar AI Sathi** (Female, warm Hindi/Hinglish persona)

Without arbitration, simultaneous AI replies would create chaotic audio collisions. Furthermore, AI agents must not chime in on every sentence when humans are having a dialogue with each other.

## Decision
Implement a dedicated `BotRouter` engine and an audio `TurnLock` mutex:
1. **Explicit Addressability**: If a user names a specific bot ("Dost", "Sathi"), the router selects that agent.
2. **Contextual Evaluation**: If humans are talking to each other without asking the bots, the router outputs `SILENCE`.
3. **Speech Mutex (TurnLock)**: Before any bot begins streaming synthesized audio to LiveKit, it must acquire the room audio lock. Only one AI bot can speak at any given millisecond.
4. **Barge-In Preemption**: If a human participant starts speaking, any active audio lock is revoked, and current TTS synthesis is aborted immediately.

## Consequences
- **Positive**: Clean room acoustics, no bot overlapping, respectful conversational behavior.
- **Negative**: Adds arbitration step latency (~50-100ms) before initiating LLM generation.
