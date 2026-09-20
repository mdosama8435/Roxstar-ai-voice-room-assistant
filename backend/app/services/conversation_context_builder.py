"""
Context builder assembling bounded multi-turn history, speaker attribution, and persona prompts.
"""

import uuid
from typing import Dict, List, Optional

from app.schemas.contracts import ConversationTurn, OrchestrationDecision
from app.schemas.llm import LLMRequest
from app.services.conversation_context import RoomContextSnapshot
from app.services.personas.prompt_builder import PersonaPromptBuilder


class ConversationContextBuilder:
    """
    Constructs an LLMRequest from OrchestrationDecision, RoomContextSnapshot, and ConversationTurn.
    Enforces bounded FIFO context windows and speaker fact isolation.
    """

    MAX_CONTEXT_TURNS = 8

    @classmethod
    def build_request(
        cls,
        decision: OrchestrationDecision,
        snapshot: RoomContextSnapshot,
        turn: ConversationTurn,
        max_context_turns: int = MAX_CONTEXT_TURNS,
    ) -> LLMRequest:
        current_speaker_id = turn.participant_identity
        current_speaker_name = turn.participant_display_name or current_speaker_id

        # 1. Extract speaker facts for current speaker
        current_profile = snapshot.speaker_profiles.get(current_speaker_id)
        speaker_facts = list(current_profile.facts) if current_profile else []

        # 2. Extract facts from other speakers without leaking them as current speaker's
        other_speaker_summaries: List[str] = []
        for spk_id, prof in snapshot.speaker_profiles.items():
            if spk_id != current_speaker_id and prof.facts:
                spk_name = getattr(prof, "name", None) or getattr(prof, "display_name", None) or spk_id
                facts_joined = ", ".join(prof.facts)
                other_speaker_summaries.append(f"{spk_name}: {facts_joined}")

        other_summary_str = "; ".join(other_speaker_summaries) if other_speaker_summaries else None

        # 3. Assemble bounded FIFO turn history (excluding the current turn)
        context_messages: List[Dict[str, str]] = []
        preceding_turns = [
            t for t in snapshot.active_turns
            if t.turn_id != turn.turn_id
        ]
        # Keep most recent max_context_turns
        bounded_turns = preceding_turns[-max_context_turns:] if len(preceding_turns) > max_context_turns else preceding_turns

        for pt in bounded_turns:
            is_bot = pt.participant_identity.lower() in ("ai_dost", "ai_sathi", "dost", "sathi")
            role = "model" if is_bot else "user"
            speaker_label = pt.participant_display_name or pt.participant_identity
            context_messages.append({
                "role": role,
                "content": f"{speaker_label}: {pt.transcript}",
            })

        # 4. Assemble system prompt
        system_prompt = PersonaPromptBuilder.build_system_prompt(
            selected_bot=decision.routing.selected_bot,
            current_speaker_name=current_speaker_name,
            speaker_facts=speaker_facts,
            other_speakers_summary=other_summary_str,
            active_topic=snapshot.current_topic,
        )

        request_id = f"llmreq-{uuid.uuid4().hex[:12]}"

        # Prefix the live user turn with the authenticated display name so the model
        # cannot confuse CURRENT SPEAKER with another participant named in history/facts.
        labeled_user_message = f"{current_speaker_name}: {turn.transcript}"

        return LLMRequest(
            request_id=request_id,
            room_id=turn.room_id,
            participant_identity=current_speaker_id,
            selected_bot=decision.routing.selected_bot,
            turn_id=turn.turn_id,
            user_message=labeled_user_message,
            system_prompt=system_prompt,
            context_messages=context_messages,
            speaker_profile=current_profile.model_dump() if current_profile else None,
            speaker_facts=speaker_facts,
        )
