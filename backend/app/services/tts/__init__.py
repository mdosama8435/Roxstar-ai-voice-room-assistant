"""Phase 3D: TTS service package."""
from backend.app.services.tts.tts_service import TTSService
from backend.app.services.tts.text_chunker import chunk_text_stream, chunk_text_sync

__all__ = ["TTSService", "chunk_text_stream", "chunk_text_sync"]
