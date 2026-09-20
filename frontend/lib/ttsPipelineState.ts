/**
 * Phase 3F.10.2 — TTS pipeline UI state from real DataChannel events.
 * Does not invent timers, latency, or simulated lifecycle.
 */

export type TTSPipelineStatus =
  | "idle"
  | "generating"
  | "publishing"
  | "completed"
  | "failed"
  | "cancelled";

export type TTSAgentId = "dost" | "sathi";

export type TTSPipelineStateByBot = Record<TTSAgentId, TTSPipelineStatus>;

export interface TtsEventInput {
  event_type: string;
  agent_id?: string | null;
  request_id?: string | null;
}

const EVENT_TO_STATUS: Record<string, TTSPipelineStatus> = {
  "tts.started": "generating",
  "tts.first_audio": "publishing",
  "tts.completed": "completed",
  "audio.published": "completed",
  "tts.failed": "failed",
  "tts.error": "failed",
  "tts.cancelled": "cancelled",
  "audio.cancelled": "cancelled",
};

export function createInitialTtsPipelineState(): TTSPipelineStateByBot {
  return { dost: "idle", sathi: "idle" };
}

export function normalizeTtsAgentId(agentId?: string | null): TTSAgentId | null {
  const a = (agentId || "").trim().toLowerCase();
  if (a === "dost") return "dost";
  if (a === "sathi") return "sathi";
  return null;
}

/**
 * Apply one real TTS lifecycle event to a single bot's status.
 * Events for an unknown / other agent do not mutate that bot's row.
 */
export function applyTtsEvent(
  state: TTSPipelineStateByBot,
  event: TtsEventInput
): TTSPipelineStateByBot {
  const agent = normalizeTtsAgentId(event.agent_id);
  if (!agent) return state;

  const nextStatus = EVENT_TO_STATUS[event.event_type];
  if (!nextStatus) return state;

  if (state[agent] === nextStatus) return state;
  return { ...state, [agent]: nextStatus };
}

/**
 * Room-level chip status: prefer in-flight, then terminal failure/cancel,
 * then completed, else idle.
 */
export function selectPipelineTtsStatus(
  state: TTSPipelineStateByBot
): TTSPipelineStatus {
  const priority: TTSPipelineStatus[] = [
    "generating",
    "publishing",
    "failed",
    "cancelled",
    "completed",
    "idle",
  ];
  for (const status of priority) {
    if (state.dost === status || state.sathi === status) {
      return status;
    }
  }
  return "idle";
}

export function isTtsPipelineActive(status: TTSPipelineStatus): boolean {
  return status === "generating" || status === "publishing";
}

export function formatTtsPipelineLabel(
  status: TTSPipelineStatus,
  isConnected: boolean
): string {
  switch (status) {
    case "generating":
      return "● GENERATING";
    case "publishing":
      return "● PUBLISHING";
    case "completed":
      return "● COMPLETED";
    case "failed":
      return "✕ FAILED";
    case "cancelled":
      return "○ CANCELLED";
    case "idle":
    default:
      return isConnected ? "○ STANDBY" : "○ Standby";
  }
}
