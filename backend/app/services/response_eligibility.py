import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.observability.logger import get_logger
from app.schemas.contracts import (
    ConversationTurn,
    ResponseEligibility,
    TriggerType,
)
from app.services.conversation_context import ContextSnapshot
from app.services.incomplete_utterance import is_incomplete_utterance

logger = get_logger("response_eligibility")


# Common conversational acknowledgement tokens (Hindi, Hinglish, English)
ACKNOWLEDGEMENT_PATTERNS = [
    r"^ok(?:ay)?\.?$",
    r"^theek\s+hai\.?$",
    r"^thik\s+hai\.?$",
    r"^samajh\s+(?:gaya|gayi|gaye)\.?$",
    r"^got\s+it\.?$",
    r"^acha\.?$",
    r"^achha\.?$",
    r"^cool\.?$",
    r"^nice\.?$",
    r"^hmm+\.?$",
    r"^ha(?:an)?\.?$",
    r"^shukriya\.?$",
    r"^thanks?(?:\s+you)?\.?$",
    r"^sahi\s+hai\.?$",
]

# Explicit bot addressing triggers
BOT_ADDRESS_PATTERNS = [
    r"\b(?:ai\s+)?dost\b",
    r"\broxstar\s+dost\b",
    r"\bsun\s+dost\b",
    r"\b(?:ai\s+)?sathi\b",
    r"\broxstar\s+sathi\b",
]

# Direct request stems
REQUEST_WORDS = {
    "samjhao", "batao", "bataiye", "explain", "tell me", "can you explain",
    "kripya", "please", "help me", "suno", "describe", "elaborate"
}

# Question words and stems
QUESTION_WORDS = {
    "kya", "kyun", "kaise", "kab", "kahan", "kaun", "kisko", "kitna", "kitne",
    "what", "why", "how", "when", "where", "who", "which", "whose", "whom"
}

# Follow-up indicators requiring previous conversational context
FOLLOW_UP_INDICATORS = [
    "thoda aur",
    "aur batao",
    "simple batao",
    "iski",
    "uski",
    "unki",
    "ispe",
    "uspe",
    "phir kya",
    "famous movie",
    "aur kya",
    "what about",
    "and then",
    "tell me more",
    "further",
]


class ResponseEligibilityService:
    """
    Deterministic rule-based response eligibility evaluator.
    Determines if a conversational turn warrants an AI companion response.
    """

    def evaluate(
        self,
        turn: ConversationTurn,
        context: Optional[ContextSnapshot] = None,
    ) -> ResponseEligibility:
        """
        Evaluates whether an incoming turn is eligible for an AI response.
        Considers current transcript semantics and bounded previous room context.
        """
        raw_text = turn.transcript.strip()
        lower_text = raw_text.lower()
        now_utc = datetime.now(timezone.utc)

        # 1. Incomplete Utterance Check
        is_inc, inc_reason = is_incomplete_utterance(raw_text)
        if is_inc:
            return ResponseEligibility(
                should_respond=False,
                reason="incomplete_sentence",
                confidence=0.90,
                trigger_type=TriggerType.INCOMPLETE_UTTERANCE,
                evidence={"indicator": inc_reason},
                created_at=now_utc,
            )

        # 2. Acknowledgements & Passive Reactions
        normalized_clean = re.sub(r"[^\w\s]", "", lower_text).strip()
        for pat in ACKNOWLEDGEMENT_PATTERNS:
            if re.match(pat, lower_text) or re.match(pat, normalized_clean):
                return ResponseEligibility(
                    should_respond=False,
                    reason="acknowledgement",
                    confidence=0.95,
                    trigger_type=TriggerType.ACKNOWLEDGEMENT,
                    evidence={"matched_pattern": pat},
                    created_at=now_utc,
                )

        # Also check common compound acknowledgements (e.g. "Okay, samajh gaya.")
        if "samajh gaya" in lower_text or "theek hai" in lower_text:
            # If no question or request word accompanies it, classify as acknowledgement
            has_request_or_question = any(w in lower_text for w in REQUEST_WORDS | QUESTION_WORDS)
            if not has_request_or_question and not lower_text.endswith("?"):
                return ResponseEligibility(
                    should_respond=False,
                    reason="acknowledgement",
                    confidence=0.90,
                    trigger_type=TriggerType.ACKNOWLEDGEMENT,
                    evidence={"phrase": "samajh gaya/theek hai"},
                    created_at=now_utc,
                )

        # 3. Explicit Bot Address (Highest Priority for Affirmative Response)
        for pat in BOT_ADDRESS_PATTERNS:
            if re.search(pat, lower_text):
                return ResponseEligibility(
                    should_respond=True,
                    reason="explicit_bot_name",
                    confidence=0.98,
                    trigger_type=TriggerType.EXPLICIT_BOT_ADDRESS,
                    evidence={"matched_name": pat},
                    created_at=now_utc,
                )

        # 4. Contextual Follow-Up Check
        # Uses previous_turn from context snapshot
        has_prior_turns = bool(context and (context.previous_turn or context.recent_turns))
        has_followup_cue = any(cue in lower_text for cue in FOLLOW_UP_INDICATORS)
        if has_followup_cue and has_prior_turns:
            prev_summary = context.previous_turn.transcript if (context and context.previous_turn) else "none"
            return ResponseEligibility(
                should_respond=True,
                reason="contextual_follow_up",
                confidence=0.88,
                trigger_type=TriggerType.FOLLOW_UP,
                evidence={
                    "followup_cue": [c for c in FOLLOW_UP_INDICATORS if c in lower_text],
                    "previous_turn_snippet": prev_summary[:40],
                    "active_topic": context.current_topic if context else None,
                },
                created_at=now_utc,
            )

        # 5. Direct Question Check
        has_question_word = any(
            re.search(rf"\b{qw}\b", lower_text) for qw in QUESTION_WORDS
        )
        if has_question_word or lower_text.endswith("?"):
            return ResponseEligibility(
                should_respond=True,
                reason="explicit_question",
                confidence=0.92,
                trigger_type=TriggerType.DIRECT_QUESTION,
                evidence={
                    "has_question_mark": lower_text.endswith("?"),
                    "question_words": [qw for qw in QUESTION_WORDS if re.search(rf"\b{qw}\b", lower_text)],
                },
                created_at=now_utc,
            )

        # 6. Direct Request Check
        has_request_stem = any(
            re.search(rf"\b{rw}\b", lower_text) for rw in REQUEST_WORDS
        )
        if has_request_stem:
            return ResponseEligibility(
                should_respond=True,
                reason="explicit_request",
                confidence=0.90,
                trigger_type=TriggerType.DIRECT_REQUEST,
                evidence={"request_words": [rw for rw in REQUEST_WORDS if re.search(rf"\b{rw}\b", lower_text)]},
                created_at=now_utc,
            )

        # 7. Casual Statement / Human Banter (Default to Silence)
        return ResponseEligibility(
            should_respond=False,
            reason="casual_statement",
            confidence=0.80,
            trigger_type=TriggerType.CASUAL_STATEMENT,
            evidence={"snippet": raw_text[:40]},
            created_at=now_utc,
        )


# Global response eligibility singleton
response_eligibility_service = ResponseEligibilityService()
