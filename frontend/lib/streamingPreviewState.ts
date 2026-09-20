/**
 * Scoped streaming-preview state transitions for AI generation UI.
 * Canonical ai.response must clear matching generating/preview state;
 * late chunks for a completed request must not revive "AI GENERATING...".
 */

export type BotType = "DOST" | "SATHI" | "NONE";

export interface StreamingPreviewState {
  requestId: string;
  bot: BotType;
  botDisplayName: string;
  text: string;
  isFinal: boolean;
}

export interface ChunkInput {
  requestId: string;
  bot: BotType;
  textDelta?: string;
  isFinal?: boolean;
  roomName?: string;
}

export interface CanonicalResponseInput {
  requestId: string;
  bot: BotType;
  roomName?: string;
  text?: string;
}

function botDisplayName(bot: BotType): string {
  return bot === "SATHI" ? "RoxStar AI Sathi" : "RoxStar AI Dost";
}

/**
 * Apply an ephemeral stream chunk. Ignores chunks for already-completed requests
 * so a late packet cannot revive the generating indicator.
 */
export function applyStreamingChunk(
  prev: StreamingPreviewState | null,
  completedRequestIds: ReadonlySet<string>,
  chunk: ChunkInput
): { preview: StreamingPreviewState | null; ignored: boolean; generatingBot: BotType | null } {
  if (!chunk.requestId || completedRequestIds.has(chunk.requestId)) {
    return { preview: prev, ignored: true, generatingBot: prev?.bot ?? null };
  }

  if (prev && prev.requestId === chunk.requestId) {
    const next: StreamingPreviewState = {
      ...prev,
      text: prev.text + (chunk.textDelta || ""),
      isFinal: Boolean(chunk.isFinal),
    };
    return { preview: next, ignored: false, generatingBot: next.bot };
  }

  // Do not replace another bot's in-flight preview with a different request
  if (prev && prev.requestId !== chunk.requestId && !completedRequestIds.has(prev.requestId)) {
    // Allow switch only when previous request already completed
    // If previous is still active, ignore foreign chunk
    return { preview: prev, ignored: true, generatingBot: prev.bot };
  }

  const preview: StreamingPreviewState = {
    requestId: chunk.requestId,
    bot: chunk.bot,
    botDisplayName: botDisplayName(chunk.bot),
    text: chunk.textDelta || "",
    isFinal: Boolean(chunk.isFinal),
  };
  return { preview, ignored: false, generatingBot: preview.bot };
}

/**
 * Apply canonical final AI response. Clears preview only when it matches this
 * request (or there is no preview). Marks request completed so late chunks die.
 */
export function applyCanonicalAiResponse(
  prev: StreamingPreviewState | null,
  completedRequestIds: ReadonlySet<string>,
  response: CanonicalResponseInput
): {
  preview: StreamingPreviewState | null;
  completedRequestIds: Set<string>;
  clearGenerating: boolean;
  generatingBot: BotType | null;
} {
  const completed = new Set(completedRequestIds);
  if (response.requestId) {
    completed.add(response.requestId);
  }

  const matchesPreview = !prev || prev.requestId === response.requestId;
  if (!matchesPreview) {
    // Another AI is still streaming — keep its preview; still mark this request done
    return {
      preview: prev,
      completedRequestIds: completed,
      clearGenerating: false,
      generatingBot: prev?.bot ?? null,
    };
  }

  return {
    preview: null,
    completedRequestIds: completed,
    clearGenerating: true,
    generatingBot: null,
  };
}
