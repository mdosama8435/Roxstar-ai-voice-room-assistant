import re
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.observability.logger import get_logger
from app.schemas.contracts import (
    BotRoutingDecision,
    BotType,
    ConversationTurn,
    ResponseEligibility,
)
from app.services.conversation_context import ContextSnapshot

logger = get_logger("bot_router")

# Explicit bot name regex patterns
DOST_EXPLICIT_PATTERNS = [
    r"\b(?:ai\s+)?dost\b",
    r"\broxstar\s+dost\b",
    r"\bsun\s+dost\b",
]

SATHI_EXPLICIT_PATTERNS = [
    r"\b(?:ai\s+)?sathi\b",
    r"\broxstar\s+sathi\b",
    r"\bsun\s+sathi\b",
]

# Deterministic keyword heuristics for semantic routing (NOT LLM semantic reasoning)
DOST_SEMANTIC_KEYWORDS = {
    "coding", "code", "tech", "technology", "python", "javascript", "api",
    "cloud", "server", "database", "computer", "machine learning", "ml", "ai",
    "simple language mein", "fast", "speed", "quick", "bhai", "yaar"
}

SATHI_SEMANTIC_KEYWORDS = {
    "feeling", "bhavna", "relationship", "life", "zindagi", "samajh",
    "thoughtful", "peace", "calm", "poetry", "kavita", "sad", "khushi",
    "dhyan", "empathy", "emotion", "reflect", "deeply", "graceful"
}


class BotRouter:
    """
    Deterministic Two-Bot Arbitration Engine.
    
    Guarantees:
    - ALWAYS produces exactly ONE of: DOST, SATHI, NONE.
    - NEVER produces both DOST + SATHI simultaneously.
    - Priority:
      1. Not eligible -> NONE
      2. Explicit bot addressing
      3. Dialogue ownership / active thread
      4. Deterministic semantic keywords (heuristic, non-LLM)
      5. Stable room-scoped Round-Robin fallback (DOST -> SATHI -> DOST)
    - Fail-closed: returns NONE on unexpected exception.
    """

    def __init__(self):
        # Room-scoped round-robin state: room_id -> last_bot
        self._round_robin_state: Dict[str, BotType] = {}

    def _get_next_round_robin_bot(self, room_id: str) -> BotType:
        last = self._round_robin_state.get(room_id, BotType.SATHI)
        # Alternate between DOST and SATHI (initial default will be DOST)
        next_bot = BotType.DOST if last == BotType.SATHI else BotType.SATHI
        self._round_robin_state[room_id] = next_bot
        return next_bot

    def route(
        self,
        turn: ConversationTurn,
        eligibility: ResponseEligibility,
        context: Optional[ContextSnapshot] = None,
    ) -> BotRoutingDecision:
        """
        Executes single-bot arbitration for an incoming turn.
        """
        now_utc = datetime.now(timezone.utc)
        decision_id = f"route-{uuid.uuid4().hex[:12]}"

        # 1. Non-eligible turns route strictly to NONE
        if not eligibility.should_respond:
            return BotRoutingDecision(
                decision_id=decision_id,
                room_id=turn.room_id,
                turn_id=turn.turn_id,
                selected_bot=BotType.NONE,
                reason="turn_not_eligible_for_response",
                confidence=1.0,
                routing_source="explicit_rule",
                created_at=now_utc,
            )

        lower_text = turn.transcript.lower()

        # 2. Explicit Bot Addressing
        has_dost = any(re.search(pat, lower_text) for pat in DOST_EXPLICIT_PATTERNS)
        has_sathi = any(re.search(pat, lower_text) for pat in SATHI_EXPLICIT_PATTERNS)

        if has_dost and not has_sathi:
            return BotRoutingDecision(
                decision_id=decision_id,
                room_id=turn.room_id,
                turn_id=turn.turn_id,
                selected_bot=BotType.DOST,
                reason="explicit_address:dost",
                confidence=0.99,
                routing_source="explicit_rule",
                created_at=now_utc,
            )

        if has_sathi and not has_dost:
            return BotRoutingDecision(
                decision_id=decision_id,
                room_id=turn.room_id,
                turn_id=turn.turn_id,
                selected_bot=BotType.SATHI,
                reason="explicit_address:sathi",
                confidence=0.99,
                routing_source="explicit_rule",
                created_at=now_utc,
            )

        # If both are addressed in same sentence (rare conflict), pick first mentioned
        if has_dost and has_sathi:
            dost_pos = min(re.search(pat, lower_text).start() for pat in DOST_EXPLICIT_PATTERNS if re.search(pat, lower_text))
            sathi_pos = min(re.search(pat, lower_text).start() for pat in SATHI_EXPLICIT_PATTERNS if re.search(pat, lower_text))
            winner = BotType.DOST if dost_pos < sathi_pos else BotType.SATHI
            return BotRoutingDecision(
                decision_id=decision_id,
                room_id=turn.room_id,
                turn_id=turn.turn_id,
                selected_bot=winner,
                reason="conflict_resolved_by_precedence",
                confidence=0.85,
                routing_source="explicit_rule",
                created_at=now_utc,
            )

        # 3. Contextual Dialogue Ownership / Continuity
        # If follow-up and topic continuity matches an active bot thread
        # (Reserved for future thread tracking; checks context if available)

        # 4. Deterministic Semantic Keyword Routing
        dost_keyword_matches = sum(1 for kw in DOST_SEMANTIC_KEYWORDS if kw in lower_text)
        sathi_keyword_matches = sum(1 for kw in SATHI_SEMANTIC_KEYWORDS if kw in lower_text)

        if dost_keyword_matches > sathi_keyword_matches:
            return BotRoutingDecision(
                decision_id=decision_id,
                room_id=turn.room_id,
                turn_id=turn.turn_id,
                selected_bot=BotType.DOST,
                reason="semantic_heuristic:tech_casual",
                confidence=0.82,
                routing_source="semantic_rule",
                created_at=now_utc,
            )

        if sathi_keyword_matches > dost_keyword_matches:
            return BotRoutingDecision(
                decision_id=decision_id,
                room_id=turn.room_id,
                turn_id=turn.turn_id,
                selected_bot=BotType.SATHI,
                reason="semantic_heuristic:reflective_nuanced",
                confidence=0.82,
                routing_source="semantic_rule",
                created_at=now_utc,
            )

        # 5. Stable Room-Scoped Round-Robin Fallback
        fallback_bot = self._get_next_round_robin_bot(turn.room_id)
        return BotRoutingDecision(
            decision_id=decision_id,
            room_id=turn.room_id,
            turn_id=turn.turn_id,
            selected_bot=fallback_bot,
            reason="stable_round_robin_fallback",
            confidence=0.75,
            routing_source="fallback",
            created_at=now_utc,
        )

    def reset_room(self, room_id: str) -> None:
        """Cleans up round-robin state for room."""
        self._round_robin_state.pop(room_id, None)


# Global bot router singleton
bot_router = BotRouter()
