import { describe, expect, it } from "vitest";
import {
  aggregateAnalytics,
  loadAnalyticsSnapshot,
  loadPipelineStore,
  normalizePipelineStore,
  recordPipelineEvent,
  type AnalyticsPipelineStore,
} from "./analytics";
import {
  persistCompletedTurn,
  type ChatHistoryStore,
  upsertHistoryMessage,
} from "./chatHistory";

function memoryStorage(seed?: Record<string, string>): Storage {
  const map = new Map<string, string>(Object.entries(seed || {}));
  return {
    get length() {
      return map.size;
    },
    clear: () => map.clear(),
    getItem: (k: string) => (map.has(k) ? map.get(k)! : null),
    key: (i: number) => Array.from(map.keys())[i] ?? null,
    removeItem: (k: string) => {
      map.delete(k);
    },
    setItem: (k: string, v: string) => {
      map.set(k, v);
    },
  } as Storage;
}

function emptyHistory(): ChatHistoryStore {
  return { version: 2, conversations: [] };
}

describe("analytics — empty & fabrication guards", () => {
  it("empty analytics state has no invented metrics", () => {
    const snap = aggregateAnalytics(emptyHistory());
    expect(snap.hasData).toBe(false);
    expect(snap.totalTurns).toBe(0);
    expect(snap.humanTurns).toBe(0);
    expect(snap.aiResponses).toBe(0);
    expect(snap.dostResponses).toBe(0);
    expect(snap.sathiResponses).toBe(0);
    expect(snap.sessionCount).toBe(0);
    expect(snap.recentSessions).toEqual([]);
    expect(snap.eligibleTurns).toBeUndefined();
    expect(snap.nonEligibleTurns).toBeUndefined();
    expect(snap.routedToDost).toBeUndefined();
    expect(snap.avgAiLatencyMs).toBeUndefined();
    expect(snap.pipeline).toBeUndefined();
  });

  it("unavailable metrics are not fabricated when turns lack orchestration/latency", () => {
    let store = emptyHistory();
    store = upsertHistoryMessage(store, {
      id: "h1",
      roomId: "r1",
      timestamp: "2026-09-20T10:00:00.000Z",
      speakerName: "Rahul",
      speakerType: "human",
      text: "Hello",
      source: "voice",
    });
    store = upsertHistoryMessage(store, {
      id: "a1",
      roomId: "r1",
      timestamp: "2026-09-20T10:00:01.000Z",
      speakerName: "RoxStar AI Dost",
      speakerType: "ai",
      text: "Hi!",
      persona: "dost",
      source: "ai",
    });
    const snap = aggregateAnalytics(store);
    expect(snap.hasData).toBe(true);
    expect(snap.humanTurns).toBe(1);
    expect(snap.aiResponses).toBe(1);
    expect(snap.dostResponses).toBe(1);
    expect(snap.eligibleTurns).toBeUndefined();
    expect(snap.avgAiLatencyMs).toBeUndefined();
    expect(snap.pipeline).toBeUndefined();
  });
});

describe("analytics — aggregation", () => {
  it("aggregates real human / AI / Dost / Sathi turn counts", () => {
    let store = emptyHistory();
    store = upsertHistoryMessage(store, {
      id: "h1",
      roomId: "room-a",
      timestamp: "2026-09-20T10:00:00.000Z",
      speakerName: "Priya",
      speakerType: "human",
      text: "AI Dost?",
      source: "voice",
      shouldRespond: true,
      selectedBot: "DOST",
    });
    store = upsertHistoryMessage(store, {
      id: "a-dost",
      roomId: "room-a",
      timestamp: "2026-09-20T10:00:02.000Z",
      speakerName: "RoxStar AI Dost",
      speakerType: "ai",
      text: "Haan!",
      persona: "dost",
      source: "ai",
      latencyMs: 800,
    });
    store = upsertHistoryMessage(store, {
      id: "h2",
      roomId: "room-a",
      timestamp: "2026-09-20T10:00:05.000Z",
      speakerName: "Priya",
      speakerType: "human",
      text: "Sathi batao",
      source: "text",
      shouldRespond: true,
      selectedBot: "SATHI",
    });
    store = upsertHistoryMessage(store, {
      id: "a-sathi",
      roomId: "room-a",
      timestamp: "2026-09-20T10:00:07.000Z",
      speakerName: "RoxStar AI Sathi",
      speakerType: "ai",
      text: "Zaroor",
      persona: "sathi",
      source: "ai",
      latencyMs: 1200,
    });
    store = upsertHistoryMessage(store, {
      id: "h3",
      roomId: "room-a",
      timestamp: "2026-09-20T10:00:08.000Z",
      speakerName: "Priya",
      speakerType: "human",
      text: "hmm ok",
      source: "voice",
      shouldRespond: false,
      selectedBot: "NONE",
    });

    const snap = aggregateAnalytics(store);
    expect(snap.totalTurns).toBe(5);
    expect(snap.humanTurns).toBe(3);
    expect(snap.aiResponses).toBe(2);
    expect(snap.dostResponses).toBe(1);
    expect(snap.sathiResponses).toBe(1);
    expect(snap.eligibleTurns).toBe(2);
    expect(snap.nonEligibleTurns).toBe(1);
    expect(snap.routedToDost).toBe(1);
    expect(snap.routedToSathi).toBe(1);
    expect(snap.routedNone).toBe(1);
    expect(snap.avgAiLatencyMs).toBe(1000);
    expect(snap.aiLatencySampleCount).toBe(2);
    expect(snap.recentSessions[0].humanParticipantCount).toBe(1);
    expect(snap.recentSessions[0].durationMs).toBe(8000);
  });

  it("duplicate message ids do not double-count", () => {
    let store = emptyHistory();
    const msg = {
      id: "dup-1",
      roomId: "room-b",
      timestamp: "2026-09-20T11:00:00.000Z",
      speakerName: "Rahul",
      speakerType: "human" as const,
      text: "Hello",
      source: "voice" as const,
      shouldRespond: true,
      selectedBot: "DOST" as const,
    };
    store = upsertHistoryMessage(store, msg);
    store = upsertHistoryMessage(store, { ...msg, text: "Hello replay" });
    const snap = aggregateAnalytics(store);
    expect(snap.totalTurns).toBe(1);
    expect(snap.humanTurns).toBe(1);
    expect(snap.eligibleTurns).toBe(1);
    expect(snap.routedToDost).toBe(1);
  });

  it("duplicate pipeline events do not double-count", () => {
    const storage = memoryStorage();
    recordPipelineEvent(
      { id: "ev-1", roomId: "r1", type: "STT_FINAL", timestamp: "2026-09-20T12:00:00.000Z" },
      storage
    );
    recordPipelineEvent(
      { id: "ev-1", roomId: "r1", type: "STT_FINAL", timestamp: "2026-09-20T12:00:01.000Z" },
      storage
    );
    recordPipelineEvent(
      { id: "ev-2", roomId: "r1", type: "AI_RESPONSE", timestamp: "2026-09-20T12:00:02.000Z" },
      storage
    );
    const pipeline = loadPipelineStore(storage);
    expect(pipeline.events).toHaveLength(2);
    const snap = aggregateAnalytics(emptyHistory(), pipeline);
    expect(snap.pipeline?.sttFinal).toBe(1);
    expect(snap.pipeline?.aiResponse).toBe(1);
    expect(snap.hasData).toBe(true);
  });

  it("session persistence / reload survives localStorage round-trip", () => {
    const storage = memoryStorage();
    persistCompletedTurn(
      {
        id: "turn-persist",
        roomId: "persist-room",
        speakerId: "human-rahul",
        speakerName: "Rahul",
        text: "Analytics check",
        isFinal: true,
        shouldRespond: true,
        selectedBot: "DOST",
        latencyMs: 500,
      },
      storage
    );
    persistCompletedTurn(
      {
        id: "ai-persist",
        roomId: "persist-room",
        speakerId: "ai_dost",
        speakerName: "RoxStar AI Dost",
        text: "Got it",
        isFinal: true,
        latencyMs: 900,
      },
      storage
    );
    recordPipelineEvent(
      {
        id: "pipe-1",
        roomId: "persist-room",
        type: "ORCHESTRATION",
        timestamp: "2026-09-20T13:00:00.000Z",
      },
      storage
    );

    const reloaded = loadAnalyticsSnapshot({ roomId: "persist-room" }, storage);
    expect(reloaded.hasData).toBe(true);
    expect(reloaded.humanTurns).toBe(1);
    expect(reloaded.aiResponses).toBe(1);
    expect(reloaded.dostResponses).toBe(1);
    expect(reloaded.eligibleTurns).toBe(1);
    expect(reloaded.routedToDost).toBe(1);
    expect(reloaded.avgAiLatencyMs).toBe(900);
    expect(reloaded.pipeline?.orchestration).toBe(1);
  });

  it("ignores non-tracked / malformed pipeline payloads", () => {
    const bad: AnalyticsPipelineStore = normalizePipelineStore({
      version: 1,
      events: [
        { id: "x", roomId: "r", type: "TOKEN_ERROR", timestamp: "t" },
        { id: "", roomId: "r", type: "STT_FINAL", timestamp: "t" },
        { id: "ok", roomId: "r", type: "STT_FINAL", timestamp: "t" },
      ],
    });
    expect(bad.events).toHaveLength(1);
    expect(bad.events[0].type).toBe("STT_FINAL");
  });
});
