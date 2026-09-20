"""
Real Gemini End-to-End Verification Runner for Phase 3C (with Rate Limit Safeguard).
Executes conversational scenarios using the official google-genai SDK,
gemini-2.5-flash, and the real RoxStar application pipeline.
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.schemas.contracts import BotType, ModalityType, TranscriptEvent
from app.services.conversation_context import conversation_context_manager
from app.services.llm.factory import get_llm_provider
from app.services.llm.gemini_provider import GeminiLLMProvider
from app.services.orchestrator import OrchestratorService
from app.services.turn_lock import turn_lock_manager


async def run_scenario(
    svc: OrchestratorService,
    room_id: str,
    turns: list[dict],
    scenario_name: str,
):
    print(f"\n{'='*70}")
    print(f"RUNNING: {scenario_name} (Room: {room_id})")
    print(f"{'='*70}")

    await turn_lock_manager.release(room_id)
    results = []

    for idx, turn_spec in enumerate(turns):
        speaker_id = turn_spec["speaker_id"]
        speaker_name = turn_spec["speaker_name"]
        text = turn_spec["text"]
        expect_response = turn_spec.get("expect_response", True)

        evt = TranscriptEvent(
            event_id=f"evt-{room_id}-{idx}",
            room_id=room_id,
            participant_identity=speaker_id,
            participant_display_name=speaker_name,
            transcript=text,
            status="final",
            modality=ModalityType.TEXT,
            timestamp=datetime.now(timezone.utc),
        )

        dec = await svc.handle_transcript_event(evt)
        assert dec is not None, f"Decision was None for turn: {text}"

        print(f"\n[Turn {idx+1}] {speaker_name}: \"{text}\"")
        print(f"  -> Eligibility: should_respond={dec.eligibility.should_respond}, trigger={dec.eligibility.trigger_type.value}, reason={dec.eligibility.reason}")
        print(f"  -> Routing: selected_bot={dec.routing.selected_bot.value}, reason={dec.routing.reason}")
        print(f"  -> Lock Acquired: {dec.turn_lock_acquired}")

        if expect_response and dec.eligibility.should_respond and dec.turn_lock_acquired:
            print("  -> Waiting for Real Gemini response...")
            ai_resp = await svc.await_llm_response(dec.turn_id, timeout=35.0)

            # If 429 occurred, wait and retry this turn once
            if not ai_resp:
                print("  -> Initial attempt failed (likely 429 quota window). Waiting 35s to retry...")
                await asyncio.sleep(35)
                # Release lock if still held
                await turn_lock_manager.release(room_id)
                # Re-submit event
                retry_evt = TranscriptEvent(
                    event_id=f"evt-{room_id}-{idx}-retry",
                    room_id=room_id,
                    participant_identity=speaker_id,
                    participant_display_name=speaker_name,
                    transcript=text,
                    status="final",
                    modality=ModalityType.TEXT,
                    timestamp=datetime.now(timezone.utc),
                )
                retry_dec = await svc.handle_transcript_event(retry_evt)
                if retry_dec and retry_dec.turn_lock_acquired:
                    ai_resp = await svc.await_llm_response(retry_dec.turn_id, timeout=35.0)

            if ai_resp:
                print(f"  -> AI Response ({ai_resp.bot.value}): \"{ai_resp.text}\"")
                print(f"  -> First-token latency: {ai_resp.first_token_latency_ms} ms")
                print(f"  -> Total pipeline latency: {ai_resp.latency_ms} ms")
                print(f"  -> Model: {ai_resp.model}, Provider: {ai_resp.provider}")
                results.append({
                    "turn_idx": idx + 1,
                    "speaker": speaker_name,
                    "input": text,
                    "bot": ai_resp.bot.value,
                    "response": ai_resp.text,
                    "first_token_ms": ai_resp.first_token_latency_ms,
                    "latency_ms": ai_resp.latency_ms,
                    "model": ai_resp.model,
                    "provider": ai_resp.provider,
                })
            else:
                print("  -> ERROR: No AI response received!")
                results.append({
                    "turn_idx": idx + 1,
                    "speaker": speaker_name,
                    "input": text,
                    "error": "Timeout or quota limit",
                })

            # Sleep 20s between calls to respect Google Free Tier 5 RPM limit
            print("  -> (Pausing 20s to respect Google Free Tier 5 RPM rate limit...)")
            await asyncio.sleep(20)
        else:
            print("  -> (No AI response expected for this turn)")
            results.append({
                "turn_idx": idx + 1,
                "speaker": speaker_name,
                "input": text,
                "response": "(Silence / Context update only)",
            })

    # Check lock is released
    lock_info = await turn_lock_manager.current_lock(room_id)
    print(f"\nFinal Room Lock status: {'LOCKED (' + lock_info.bot.value + ')' if lock_info else 'RELEASED (None)'}")

    return results


async def main():
    print(f"Configured LLM_PROVIDER: {settings.llm_provider}")
    print(f"Configured LLM_MODEL: {settings.llm_model}")
    print(f"Configured GEMINI_API_KEY: {'CONFIGURED' if settings.effective_gemini_api_key else 'MISSING'}")

    provider = get_llm_provider()
    print(f"Resolved Provider Type: {type(provider).__name__}")
    assert isinstance(provider, GeminiLLMProvider), "Expected GeminiLLMProvider!"

    # Load existing successful results if present
    results_path = os.path.join(os.getcwd(), "scenario_results.json")
    all_scenarios = {}
    if os.path.exists(results_path):
        try:
            with open(results_path, "r", encoding="utf-8") as f:
                all_scenarios = json.load(f)
        except Exception:
            pass

    svc = OrchestratorService()

    # SCENARIO 1: "AI kya hota hai?"
    if "Scenario 1" not in all_scenarios or "error" in str(all_scenarios["Scenario 1"]):
        s1_turns = [
            {"speaker_id": "human-rahul", "speaker_name": "Rahul", "text": "AI kya hota hai?", "expect_response": True}
        ]
        all_scenarios["Scenario 1"] = await run_scenario(svc, "room-sc1", s1_turns, "Scenario 1: AI Explanation")
    else:
        print("Scenario 1 already completed. Skipping.")

    # SCENARIO 2: "What is cloud computing?"
    if "Scenario 2" not in all_scenarios or "error" in str(all_scenarios["Scenario 2"]):
        s2_turns = [
            {"speaker_id": "human-rahul", "speaker_name": "Rahul", "text": "What is cloud computing?", "expect_response": True}
        ]
        all_scenarios["Scenario 2"] = await run_scenario(svc, "room-sc2", s2_turns, "Scenario 2: Cloud Computing (English)")
    else:
        print("Scenario 2 already completed. Skipping.")

    # SCENARIO 3: "Shah Rukh Khan kaun hai?" then "Unki koi famous movie batao."
    if "Scenario 3" not in all_scenarios or any("error" in t for t in all_scenarios["Scenario 3"]):
        s3_turns = [
            {"speaker_id": "human-rahul", "speaker_name": "Rahul", "text": "Shah Rukh Khan kaun hai?", "expect_response": True},
            {"speaker_id": "human-rahul", "speaker_name": "Rahul", "text": "Unki koi famous movie batao.", "expect_response": True},
        ]
        all_scenarios["Scenario 3"] = await run_scenario(svc, "room-sc3-v2", s3_turns, "Scenario 3: SRK Follow-up & Pronoun Resolution")
    else:
        print("Scenario 3 already completed. Skipping.")

    # SCENARIO 4: Rahul: "AI kya hota hai?" -> Priya: "Thoda aur simple batao."
    if "Scenario 4" not in all_scenarios or any("error" in t for t in all_scenarios["Scenario 4"]):
        s4_turns = [
            {"speaker_id": "human-rahul", "speaker_name": "Rahul", "text": "AI kya hota hai?", "expect_response": True},
            {"speaker_id": "human-priya", "speaker_name": "Priya", "text": "Thoda aur simple batao.", "expect_response": True},
        ]
        all_scenarios["Scenario 4"] = await run_scenario(svc, "room-sc4-v2", s4_turns, "Scenario 4: Multi-User Context Follow-up (Rahul -> Priya)")
    else:
        print("Scenario 4 already completed. Skipping.")

    # SCENARIO 5:
    # Rahul: "Mera naam Rahul hai."
    # Rahul: "Mujhe cricket pasand hai."
    # Rahul: "Maine tumhe kya bataya tha?"
    if "Scenario 5" not in all_scenarios or any("error" in t for t in all_scenarios["Scenario 5"]):
        s5_turns = [
            {"speaker_id": "human-rahul", "speaker_name": "Rahul", "text": "Mera naam Rahul hai.", "expect_response": False},
            {"speaker_id": "human-rahul", "speaker_name": "Rahul", "text": "Mujhe cricket pasand hai.", "expect_response": False},
            {"speaker_id": "human-rahul", "speaker_name": "Rahul", "text": "Maine tumhe kya bataya tha?", "expect_response": True},
        ]
        all_scenarios["Scenario 5"] = await run_scenario(svc, "room-sc5-v2", s5_turns, "Scenario 5: Speaker Memory Facts & Retention")
    else:
        print("Scenario 5 already completed. Skipping.")

    print("\n" + "="*70)
    print("ALL 5 REAL GEMINI SCENARIOS COMPLETED")
    print("="*70)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(all_scenarios, f, indent=2, ensure_ascii=False)
    print(f"Results saved to {results_path}")

if __name__ == "__main__":
    asyncio.run(main())
