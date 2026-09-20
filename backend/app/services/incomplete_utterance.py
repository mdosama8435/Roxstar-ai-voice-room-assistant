import re
from typing import Tuple


# Trailing conjunctions in Hindi/Hinglish/English that indicate an utterance was cut off mid-thought
TRAILING_CONJUNCTIONS = {
    "aur", "and", "ya", "or", "lekin", "but", "ki", "toh", "so", "bhi", "tatha", "evam", "kintu", "parantu"
}

# Trailing postpositions / prepositions indicating incomplete grammatical phrase
TRAILING_POSTPOSITIONS = {
    "mein", "me", "ke", "ka", "ki", "ko", "se", "par", "pe", "of", "in", "with", "to", "for", "about", "on", "at", "from"
}

# Trailing question words with no verb or object (e.g., "AI kya...", "system kyun...")
TRAILING_HANGING_QUESTION_WORDS = {
    "kya", "kyun", "kaise", "kab", "kahan", "kaun", "what", "why", "how", "when", "where"
}


def is_incomplete_utterance(text: str) -> Tuple[bool, str]:
    """
    Deterministic rule-based heuristics evaluating whether an utterance transcript
    is grammatically or phonetically incomplete and awaiting continuation.

    Returns:
        (is_incomplete: bool, reason: str)
    """
    cleaned = text.strip()
    if not cleaned:
        return True, "empty_transcript"

    # 1. Trailing ellipsis
    if cleaned.endswith("...") or cleaned.endswith("…") or cleaned.endswith(".."):
        return True, "trailing_ellipsis"

    # Remove trailing punctuation like commas, dashes, trailing periods (single)
    # but preserve question marks if present
    has_question_mark = cleaned.endswith("?")
    normalized = re.sub(r"[,\-—\.]+$", "", cleaned).strip().lower()
    words = normalized.split()

    if not words:
        return True, "empty_after_stripping"

    last_word = words[-1]

    # 2. Trailing conjunctions (e.g. "Cloud computing kya hai aur...")
    if last_word in TRAILING_CONJUNCTIONS:
        return True, f"trailing_conjunction:{last_word}"

    # 3. Trailing postpositions/prepositions (e.g. "Shah Rukh Khan ki...", "Cloud computing mein...")
    if last_word in TRAILING_POSTPOSITIONS:
        return True, f"trailing_postposition:{last_word}"

    # 4. Trailing hanging question word without completion verb
    # e.g., "AI kya" -> incomplete. But "AI kya hota hai?" is complete.
    if len(words) > 1 and last_word in TRAILING_HANGING_QUESTION_WORDS and not has_question_mark:
        return True, f"trailing_question_marker:{last_word}"

    return False, "complete"
