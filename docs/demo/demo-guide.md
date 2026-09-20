# Demo Guide — RoxStar AI Voice Room Assistant

Quick path for reviewers after Phase 3F implementation.

## 1. Start services

**Backend** (repo root):

```bash
pip install -r backend/requirements.txt
set PYTHONPATH=.
uvicorn backend.app.main:app --reload --port 8000
```

Confirm: http://127.0.0.1:8000/health

**Frontend**:

```bash
cd frontend
npm install
npm run dev
```

**Optional agent worker**: `python -m agents.app.main`

Ensure `.env` / `backend/.env` contain LiveKit + Sarvam + Gemini (and optional NVIDIA) credentials. See root README.

## 2. Open the room

- http://127.0.0.1:3000/room/demo
- Or auto-join: http://127.0.0.1:3000/room/demo?room=roxstar-test&name=Rahul&auto=1

Second human: another browser/profile with `name=Priya` and the **same** `room`.

## 3. What to verify

1. Topbar shows **LIVE** after connect.
2. Human cards appear; AI Dost / AI Sathi appear when the AI pipeline is connected.
3. Mic on → speak Hindi/Hinglish/English → transcripts appear.
4. Text chat works and can trigger orchestration.
5. “AI Dost, …” / “AI Sathi, …” route to the correct bot (one response, turn lock).
6. Interrupt during AI speech (barge-in) — old audio should stop.
7. Leave → rejoin → LIVE again.
8. Sidebar tools: Documentation, Analytics, Scenarios, Summary, Settings (local tools only).

## 4. If AI does not reply

- Check Gemini quota (HTTP 429) and NVIDIA fallback configuration.
- Confirm backend logs (no secrets) for STT / LLM / TTS errors.
- Confirm LiveKit URL/keys and Sarvam STT/TTS keys are set.

## 5. Further reading

- Root [README.md](../README.md)
- [docs/orchestration.md](../orchestration.md)
- [docs/architecture/sequence-diagrams.md](../architecture/sequence-diagrams.md)
