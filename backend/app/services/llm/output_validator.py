"""
Speech-oriented output validation and normalization service.
Ensures LLM text is clean, speech-friendly, bounded, and free of markdown syntax.
"""

import re
from typing import Optional


class OutputValidator:
    """
    Validates and cleanses raw LLM text output before LiveKit broadcasting or downstream TTS.
    """

    DEFAULT_MAX_SPEECH_LENGTH = 600

    @classmethod
    def clean_speech_text(cls, text: str) -> str:
        """
        Strips markdown headers, code blocks, raw URLs, and formatting artifacts.
        """
        if not text:
            return ""

        # 1. Remove code blocks (```code```)
        cleaned = re.sub(r"```[\s\S]*?```", "", text)

        # 2. Remove inline code backticks (`code`)
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)

        # 3. Remove markdown headers (#, ##, ###)
        cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)

        # 4. Remove markdown bold/italics (*text*, **text**, _text_)
        cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
        cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
        cleaned = re.sub(r"_([^_]+)_", r"\1", cleaned)

        # 5. Remove markdown bullet points (* item, - item, 1. item)
        cleaned = re.sub(r"^\s*[-*+]\s+", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"^\s*\d+\.\s+", "", cleaned, flags=re.MULTILINE)

        # 6. Convert markdown links [title](url) to title
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)

        # 7. Remove raw URLs
        cleaned = re.sub(r"https?://\S+", "", cleaned)

        # 8. Collapse whitespace and newlines
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        return cleaned

    @classmethod
    def truncate_at_sentence_boundary(cls, text: str, max_length: int) -> str:
        """
        Truncates text at the nearest sentence boundary within max_length to avoid
        cutting mid-sentence. Supports Hindi/Purna Viram (।) and standard punctuation.
        """
        if len(text) <= max_length:
            return text

        candidate = text[:max_length]
        # Match punctuation followed by space or end
        matches = list(re.finditer(r"([.!?।])(\s|$)", candidate))
        if matches:
            last_match = matches[-1]
            end_pos = last_match.end(1)
            return candidate[:end_pos].strip()

        # If no sentence boundary found in candidate, search for space
        last_space = candidate.rfind(" ")
        if last_space > 0:
            return candidate[:last_space].strip() + "..."

        return candidate.strip()

    @classmethod
    def validate(cls, raw_text: Optional[str], max_length: int = DEFAULT_MAX_SPEECH_LENGTH) -> str:
        """
        Runs complete cleaning, validation, and length enforcement.
        Raises ValueError if text is empty or unviable for speech.
        """
        if not raw_text:
            raise ValueError("LLM generated empty response output")

        cleaned = cls.clean_speech_text(raw_text)
        if not cleaned or not cleaned.strip():
            raise ValueError("LLM response contains no valid spoken text after cleaning")

        final_text = cls.truncate_at_sentence_boundary(cleaned, max_length)
        if not final_text:
            raise ValueError("LLM response became empty after truncation")

        return final_text
