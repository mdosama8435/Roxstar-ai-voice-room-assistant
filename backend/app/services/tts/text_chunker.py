"""
Phase 3D: TTS Text Chunker — Sentence/phrase boundary buffering layer.

Chunking Policy:
- Primary boundaries: sentence-ending punctuation (. ? ! ।)
- Secondary fallback: comma (,) when buffer exceeds max_chunk_chars
- Never splits in the middle of a word
- Configurable min_chunk_chars and max_chunk_chars

Goal: Low time-to-first-audio without producing unnatural micro-fragments.
The chunker prevents sending every raw LLM token directly to TTS while
also avoiding waiting for the entire LLM response before starting synthesis.

Example flow:
  LLM stream: "AI basically ek technology hai. Jo machines ko..."
  Chunker yields: "AI basically ek technology hai."  (sentence boundary hit)
  Next chunk: "Jo machines ko..."  (continues buffering)
"""

import re
from typing import AsyncIterator, Optional


# Primary sentence-ending boundaries
_PRIMARY_BOUNDARY = re.compile(r'([.?!।])\s*')

# Secondary: comma boundary (only used as fallback when buffer is large)
_SECONDARY_BOUNDARY = re.compile(r'([,;])\s*')

# Word boundary (for force-flush at max_chars without splitting words)
_WORD_BOUNDARY = re.compile(r'\s+')


def _find_primary_split(text: str) -> Optional[int]:
    """Returns index just after the last primary sentence boundary in text, or None."""
    match = None
    for m in _PRIMARY_BOUNDARY.finditer(text):
        match = m
    if match:
        return match.end()
    return None


def _find_secondary_split(text: str) -> Optional[int]:
    """Returns index just after the last secondary (comma/semicolon) boundary in text, or None."""
    match = None
    for m in _SECONDARY_BOUNDARY.finditer(text):
        match = m
    if match:
        return match.end()
    return None


def _find_word_boundary_split(text: str, max_pos: int) -> int:
    """
    Finds the last word boundary (whitespace) at or before max_pos in text.
    Returns max_pos if no whitespace found (forces hard split at limit).
    """
    candidate = text[:max_pos]
    last_space = candidate.rfind(' ')
    if last_space > 0:
        return last_space + 1  # include the space in this chunk
    return max_pos  # no word boundary found, split at max


async def chunk_text_stream(
    token_stream: AsyncIterator[str],
    min_chunk_chars: int = 40,
    max_chunk_chars: int = 250,
) -> AsyncIterator[str]:
    """
    Transforms a raw LLM token stream into sentence/phrase-boundary-aligned chunks
    suitable for streaming TTS synthesis.

    Args:
        token_stream: Async iterator of raw LLM token strings
        min_chunk_chars: Minimum chars before considering a split (prevents micro-fragments)
        max_chunk_chars: Maximum chars before forcing a flush at word boundary

    Yields:
        str: Non-empty text chunks ready for TTS, aligned at natural speech boundaries.

    Chunking rules:
    1. Accumulate tokens into buffer.
    2. When buffer >= min_chunk_chars AND a primary boundary exists:
       → yield text up to and including the boundary; keep remainder.
    3. When buffer >= max_chunk_chars AND no primary boundary:
       → try secondary boundary (comma/semicolon)
       → if still none: force split at word boundary
    4. At stream end: yield any remaining buffer content.
    """
    buffer = ""

    async for token in token_stream:
        if not token:
            continue
        buffer += token

        # Try primary boundary split when min size reached
        if len(buffer) >= min_chunk_chars:
            split_pos = _find_primary_split(buffer)
            if split_pos is not None:
                chunk = buffer[:split_pos].strip()
                buffer = buffer[split_pos:].lstrip()
                if chunk:
                    yield chunk
                continue

        # Force flush at max size using secondary or word boundary
        if len(buffer) >= max_chunk_chars:
            # Try secondary (comma) boundary first
            split_pos = _find_secondary_split(buffer)
            if split_pos is not None and split_pos >= min_chunk_chars:
                chunk = buffer[:split_pos].strip()
                buffer = buffer[split_pos:].lstrip()
                if chunk:
                    yield chunk
                continue

            # Fall back to word boundary to avoid splitting mid-word
            split_pos = _find_word_boundary_split(buffer, max_chunk_chars)
            chunk = buffer[:split_pos].strip()
            buffer = buffer[split_pos:].lstrip()
            if chunk:
                yield chunk

    # Flush remaining buffer at stream end
    remaining = buffer.strip()
    if remaining:
        yield remaining


def chunk_text_sync(
    full_text: str,
    min_chunk_chars: int = 40,
    max_chunk_chars: int = 250,
) -> list:
    """
    Synchronous version for testing and non-streaming use.
    Splits a complete text string into chunks following the same boundary rules.

    Returns:
        List of str chunks.
    """
    chunks = []
    buffer = full_text

    while buffer:
        if len(buffer) <= max_chunk_chars:
            # Try primary boundary
            if len(buffer) >= min_chunk_chars:
                split_pos = _find_primary_split(buffer)
                if split_pos is not None:
                    chunk = buffer[:split_pos].strip()
                    buffer = buffer[split_pos:].lstrip()
                    if chunk:
                        chunks.append(chunk)
                    continue

            # If buffer is small enough, just flush it
            if buffer.strip():
                chunks.append(buffer.strip())
            break

        # Buffer exceeds max_chunk_chars
        split_pos = _find_primary_split(buffer[:max_chunk_chars + 20])
        if split_pos is not None and split_pos >= min_chunk_chars:
            chunk = buffer[:split_pos].strip()
            buffer = buffer[split_pos:].lstrip()
            if chunk:
                chunks.append(chunk)
            continue

        # Secondary boundary
        split_pos = _find_secondary_split(buffer[:max_chunk_chars + 20])
        if split_pos is not None and split_pos >= min_chunk_chars:
            chunk = buffer[:split_pos].strip()
            buffer = buffer[split_pos:].lstrip()
            if chunk:
                chunks.append(chunk)
            continue

        # Word boundary
        split_pos = _find_word_boundary_split(buffer, max_chunk_chars)
        chunk = buffer[:split_pos].strip()
        buffer = buffer[split_pos:].lstrip()
        if chunk:
            chunks.append(chunk)

    return [c for c in chunks if c]
