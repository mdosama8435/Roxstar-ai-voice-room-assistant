# Bot Routing & Multi-Party Arbitration Strategy

In a multi-user room with two AI agents and two or more human participants, coordinating turns is critical to prevent awkward cross-talk, unnecessary chatter, and unnatural AI behavior.

---

## 1. The Arbitration Problem
1. **The Over-Eager Bot Problem**: If an AI responds to every sentence uttered in the room, it interrupts human-to-human banter.
2. **The Dual-Speaker Collision**: If both Roxstar AI Dost and Roxstar AI Sathi generate speech at the same time, the audio turns into noise.
3. **The Identity Ambiguity**: Knowing who the user meant when asking "What do you think?"

---

## 2. Decision Logic Pipeline

When an incoming turn is closed by the Turn Detector:

```
                  [ Incoming Finished Turn ]
                              │
                              ▼
               ┌──────────────────────────────┐
               │  Step 1: Direct Mention Check │
               │  Contains "Dost" or "Sathi"?  │
               └──────────────┬───────────────┘
                              │
             Yes ─────────────┴───────────── No
              │                               │
              ▼                               ▼
       Route directly to          ┌──────────────────────────────┐
       addressed persona          │ Step 2: Human Address Check  │
                                  │ Addressed to another human?  │
                                  └───────────┬──────────────────┘
                                              │
                             Yes ─────────────┴───────────── No
                              │                               │
                              ▼                               ▼
                      Decision: SILENCE          ┌──────────────────────────────┐
                      (Stay quiet, humans        │ Step 3: Explicit Bot Prompt? │
                       are speaking)             │ Open query / Help requested? │
                                                 └────────────┬─────────────────┘
                                                              │
                                             Yes ─────────────┴───────────── No
                                              │                               │
                                              ▼                               ▼
                                   ┌─────────────────────┐            Decision: SILENCE
                                   │ Step 4: Persona Fit │
                                   │ Dost vs Sathi Score │
                                   └──────────┬──────────┘
                                              │
                                              ▼
                                   Acquire TurnLock Mutex
                                              │
                                              ▼
                                   Stream Selected Persona
```

---

## 3. TurnLock Mutex Specification
- A distributed lock (backed by Redis or an in-memory asyncio Lock in single-node mode).
- Lock key: `room:{room_id}:speech_lock`.
- TTL: Automatically expires after 15 seconds to prevent deadlock if an agent crashes during playback.
- Preemption: Human voice activity detection emits a `BargeInSignal`, which immediately forces release of the lock and halts TTS playback.
