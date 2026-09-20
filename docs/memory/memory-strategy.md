# Memory Strategy: Ephemeral Turns and Long-Term Profiles

Maintaining context across multiple human speakers and two AI participants requires a two-tiered memory architecture.

---

## 1. Ephemeral Session Memory (Short-Term)
- **Store**: In-memory cache or Redis key per `room_id`.
- **Sliding Window Context**: Holds the last $N$ turns (e.g., 10-15 turns) of mixed voice and text messages.
- **Shared Modality**: Transcripts originating from audio STT and messages originating from the text chat widget are unified into a single chronological timeline.
- **Turn Attribution**: Every turn explicitly records `speaker_id`, `speaker_name`, `modality` (`VOICE` or `TEXT`), and `timestamp`.

---

## 2. Participant Profile & Fact Extraction (Mid/Long-Term)
- **Speaker Profiling**: Stored as structured `SpeakerProfile` objects:
  - Participant ID & display name.
  - Preferred language & linguistic register (e.g., casual Hinglish vs. formal English).
  - Explicit extracted facts (e.g., "Rahul is a backend engineer based in Bengaluru").
- **Extraction Protocol**: After conversational milestones or direct revelations, a background worker extracts salient facts without blocking real-time speech response.

---

## 3. Semantic Memory & Vector Storage (Planned: PostgreSQL + pgvector)
- **Cross-Session Retrieval**: Allows returning participants to be recognized and past room decisions or action items recalled.
- **Cosine Similarity Search**: Queries vector embeddings of past meeting topics when relevant queries arise.

---

## 4. Context Window Protection & Summarization
- **Threshold Limit**: If the session turn history exceeds model context budgets (e.g., > 3,000 tokens), an incremental rolling summarizer compresses earlier turns into a `RoomSummary` state.
- **Recent Turn Preservation**: The most recent 5 turns are always preserved verbatim to maintain conversational continuity.
