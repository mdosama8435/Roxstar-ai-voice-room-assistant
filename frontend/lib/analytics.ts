/**
 * Session analytics derived from locally persisted chat history + pipeline events.
 * Never invents metrics — optional fields are omitted when sources are absent.
 */

import {
  type ChatHistoryConversation,
  type ChatHistoryStore,
  loadChatHistoryStore,
} from "./chatHistory";

export const ANALYTICS_PIPELINE_STORAGE_KEY = "roxstar-analytics-pipeline";
export const MAX_PIPELINE_EVENTS = 500;

export type AnalyticsPipelineEvent = {
  id: string;
  roomId: string;
  type: string;
  timestamp: string;
};

export type AnalyticsPipelineStore = {
  version: 1;
  events: AnalyticsPipelineEvent[];
};

/** Pipeline types we surface (safe, non-secret event log types). */
export const TRACKED_PIPELINE_TYPES = new Set([
  "STT_FINAL",
  "STT_REMOTE",
  "ORCHESTRATION",
  "AI_RESPONSE",
]);

export type SessionSummary = {
  roomId: string;
  messageCount: number;
  humanTurns: number;
  aiResponses: number;
  humanParticipantCount: number;
  startedAt: string;
  updatedAt: string;
  /** Only when both timestamps parse to valid dates. */
  durationMs?: number;
};

export type AnalyticsSnapshot = {
  hasData: boolean;
  totalTurns: number;
  humanTurns: number;
  aiResponses: number;
  dostResponses: number;
  sathiResponses: number;
  /** Only when at least one message carries orchestration shouldRespond. */
  eligibleTurns?: number;
  nonEligibleTurns?: number;
  /** Dost/Sathi routing from orchestration selectedBot (human turns). */
  routedToDost?: number;
  routedToSathi?: number;
  routedNone?: number;
  /** Only when ≥1 AI turn has a finite latencyMs. */
  avgAiLatencyMs?: number;
  aiLatencySampleCount?: number;
  sessionCount: number;
  recentSessions: SessionSummary[];
  /** Only when pipeline event store has tracked events. */
  pipeline?: {
    sttFinal: number;
    sttRemote: number;
    orchestration: number;
    aiResponse: number;
  };
  /** Room filter used for this snapshot (if any). */
  scopeRoomId?: string | null;
};

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof localStorage !== "undefined";
}

function emptyPipelineStore(): AnalyticsPipelineStore {
  return { version: 1, events: [] };
}

export function normalizePipelineStore(raw: unknown): AnalyticsPipelineStore {
  if (!raw || typeof raw !== "object") return emptyPipelineStore();
  const obj = raw as Partial<AnalyticsPipelineStore>;
  if (!Array.isArray(obj.events)) return emptyPipelineStore();
  const events: AnalyticsPipelineEvent[] = [];
  const seen = new Set<string>();
  for (const e of obj.events) {
    if (!e || typeof e !== "object") continue;
    const id = typeof e.id === "string" ? e.id : "";
    const roomId = typeof e.roomId === "string" ? e.roomId : "";
    const type = typeof e.type === "string" ? e.type : "";
    const timestamp = typeof e.timestamp === "string" ? e.timestamp : "";
    if (!id || !roomId || !type || seen.has(id)) continue;
    if (!TRACKED_PIPELINE_TYPES.has(type)) continue;
    seen.add(id);
    events.push({ id, roomId, type, timestamp: timestamp || new Date().toISOString() });
  }
  return { version: 1, events: events.slice(-MAX_PIPELINE_EVENTS) };
}

export function loadPipelineStore(
  storage: Pick<Storage, "getItem"> | null = isBrowser() ? localStorage : null
): AnalyticsPipelineStore {
  if (!storage) return emptyPipelineStore();
  try {
    const raw = storage.getItem(ANALYTICS_PIPELINE_STORAGE_KEY);
    if (!raw) return emptyPipelineStore();
    return normalizePipelineStore(JSON.parse(raw));
  } catch {
    return emptyPipelineStore();
  }
}

export function savePipelineStore(
  store: AnalyticsPipelineStore,
  storage: Pick<Storage, "setItem"> | null = isBrowser() ? localStorage : null
): void {
  if (!storage) return;
  try {
    storage.setItem(
      ANALYTICS_PIPELINE_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        events: store.events.slice(-MAX_PIPELINE_EVENTS),
      })
    );
  } catch {
    // Quota / private mode — analytics is best-effort.
  }
}

/**
 * Record a pipeline event by durable id (no double-count on replay).
 */
export function recordPipelineEvent(
  input: AnalyticsPipelineEvent,
  storage: Pick<Storage, "getItem" | "setItem"> | null = isBrowser() ? localStorage : null
): AnalyticsPipelineStore {
  if (!input.id || !input.roomId || input.roomId === "unknown") {
    return loadPipelineStore(storage);
  }
  if (!TRACKED_PIPELINE_TYPES.has(input.type)) {
    return loadPipelineStore(storage);
  }
  const store = loadPipelineStore(storage);
  if (store.events.some((e) => e.id === input.id)) return store;
  const next: AnalyticsPipelineStore = {
    version: 1,
    events: [...store.events, { ...input }].slice(-MAX_PIPELINE_EVENTS),
  };
  savePipelineStore(next, storage);
  return next;
}

function durationMs(startedAt: string, updatedAt: string): number | undefined {
  const a = Date.parse(startedAt);
  const b = Date.parse(updatedAt);
  if (!Number.isFinite(a) || !Number.isFinite(b) || b < a) return undefined;
  return b - a;
}

function summarizeSession(conv: ChatHistoryConversation): SessionSummary {
  const humanTurns = conv.messages.filter((m) => m.speakerType === "human").length;
  const aiResponses = conv.messages.filter((m) => m.speakerType === "ai").length;
  const summary: SessionSummary = {
    roomId: conv.roomId,
    messageCount: conv.messageCount,
    humanTurns,
    aiResponses,
    humanParticipantCount: conv.participantNames.length,
    startedAt: conv.startedAt,
    updatedAt: conv.updatedAt,
  };
  const d = durationMs(conv.startedAt, conv.updatedAt);
  if (d !== undefined) summary.durationMs = d;
  return summary;
}

/**
 * Aggregate analytics from chat history (+ optional pipeline store).
 * Pass roomId to scope to one session; omit for all stored sessions.
 */
export function aggregateAnalytics(
  history: ChatHistoryStore,
  pipeline: AnalyticsPipelineStore = emptyPipelineStore(),
  options?: { roomId?: string | null }
): AnalyticsSnapshot {
  const scopeRoomId = options?.roomId?.trim() || null;
  const conversations = scopeRoomId
    ? history.conversations.filter((c) => c.roomId === scopeRoomId)
    : history.conversations;

  const messages = conversations.flatMap((c) => c.messages);

  let humanTurns = 0;
  let aiResponses = 0;
  let dostResponses = 0;
  let sathiResponses = 0;
  let eligibleTurns = 0;
  let nonEligibleTurns = 0;
  let eligibilityObserved = 0;
  let routedToDost = 0;
  let routedToSathi = 0;
  let routedNone = 0;
  let routingObserved = 0;
  let latencySum = 0;
  let latencyCount = 0;

  for (const m of messages) {
    if (m.speakerType === "human") {
      humanTurns += 1;
      if (typeof m.shouldRespond === "boolean") {
        eligibilityObserved += 1;
        if (m.shouldRespond) eligibleTurns += 1;
        else nonEligibleTurns += 1;
      }
      if (m.selectedBot === "DOST") {
        routingObserved += 1;
        routedToDost += 1;
      } else if (m.selectedBot === "SATHI") {
        routingObserved += 1;
        routedToSathi += 1;
      } else if (m.selectedBot === "NONE") {
        routingObserved += 1;
        routedNone += 1;
      }
    } else if (m.speakerType === "ai") {
      aiResponses += 1;
      if (m.persona === "dost") dostResponses += 1;
      else if (m.persona === "sathi") sathiResponses += 1;
      if (typeof m.latencyMs === "number" && Number.isFinite(m.latencyMs) && m.latencyMs >= 0) {
        latencySum += m.latencyMs;
        latencyCount += 1;
      }
    }
  }

  const recentSessions = [...conversations]
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
    .slice(0, 12)
    .map(summarizeSession);

  const pipelineEvents = scopeRoomId
    ? pipeline.events.filter((e) => e.roomId === scopeRoomId)
    : pipeline.events;

  const snapshot: AnalyticsSnapshot = {
    hasData: messages.length > 0 || pipelineEvents.length > 0,
    totalTurns: messages.length,
    humanTurns,
    aiResponses,
    dostResponses,
    sathiResponses,
    sessionCount: conversations.length,
    recentSessions,
    scopeRoomId,
  };

  if (eligibilityObserved > 0) {
    snapshot.eligibleTurns = eligibleTurns;
    snapshot.nonEligibleTurns = nonEligibleTurns;
  }
  if (routingObserved > 0) {
    snapshot.routedToDost = routedToDost;
    snapshot.routedToSathi = routedToSathi;
    snapshot.routedNone = routedNone;
  }
  if (latencyCount > 0) {
    snapshot.avgAiLatencyMs = Math.round(latencySum / latencyCount);
    snapshot.aiLatencySampleCount = latencyCount;
  }
  if (pipelineEvents.length > 0) {
    snapshot.pipeline = {
      sttFinal: pipelineEvents.filter((e) => e.type === "STT_FINAL").length,
      sttRemote: pipelineEvents.filter((e) => e.type === "STT_REMOTE").length,
      orchestration: pipelineEvents.filter((e) => e.type === "ORCHESTRATION").length,
      aiResponse: pipelineEvents.filter((e) => e.type === "AI_RESPONSE").length,
    };
  }

  return snapshot;
}

export function loadAnalyticsSnapshot(
  options?: { roomId?: string | null },
  storage: Pick<Storage, "getItem"> | null = isBrowser() ? localStorage : null
): AnalyticsSnapshot {
  return aggregateAnalytics(loadChatHistoryStore(storage), loadPipelineStore(storage), options);
}

export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}
