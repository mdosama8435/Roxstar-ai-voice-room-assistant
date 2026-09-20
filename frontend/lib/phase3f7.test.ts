import { describe, expect, it } from "vitest";
import {
  DOC_SECTION_IDS,
  DOCUMENTATION_SECTIONS,
  getDocumentationSectionIds,
} from "./documentationContent";
import {
  buildConversationSummary,
  emptyConversationSummary,
} from "./conversationSummary";
import {
  APP_NAV_ROUTES,
  looksLikeSecretKey,
  pickSafeSystemStatus,
  readLocalDataStats,
  sanitizeForDisplay,
} from "./settingsInfo";
import { upsertHistoryMessage, type ChatHistoryStore } from "./chatHistory";

function emptyHistory(): ChatHistoryStore {
  return { version: 2, conversations: [] };
}

describe("documentationContent", () => {
  it("includes all required assignment sections", () => {
    const ids = getDocumentationSectionIds();
    for (const required of DOC_SECTION_IDS) {
      expect(ids).toContain(required);
    }
    expect(DOCUMENTATION_SECTIONS.length).toBe(DOC_SECTION_IDS.length);
    for (const section of DOCUMENTATION_SECTIONS) {
      expect(section.title.length).toBeGreaterThan(0);
      expect(section.paragraphs.length).toBeGreaterThan(0);
    }
  });
});

describe("conversationSummary", () => {
  it("empty state when no history", () => {
    const view = buildConversationSummary(emptyHistory());
    expect(view.empty).toBe(true);
    expect(view.roomId).toBeNull();
    expect(view.humanTurns).toBe(0);
    expect(view.aiTurns).toBe(0);
    expect(view.topicLines).toEqual([]);
    expect(view.recentTurns).toEqual([]);
    expect(emptyConversationSummary().empty).toBe(true);
  });

  it("derives stats from real stored history only", () => {
    let store = emptyHistory();
    store = upsertHistoryMessage(store, {
      id: "h1",
      roomId: "room-sum",
      timestamp: "2026-09-20T10:00:00.000Z",
      speakerName: "Rahul",
      speakerType: "human",
      text: "AI kya hota hai?",
      source: "voice",
    });
    store = upsertHistoryMessage(store, {
      id: "a1",
      roomId: "room-sum",
      timestamp: "2026-09-20T10:00:02.000Z",
      speakerName: "RoxStar AI Dost",
      speakerType: "ai",
      text: "AI ek smart system hai",
      persona: "dost",
      source: "ai",
    });
    store = upsertHistoryMessage(store, {
      id: "a2",
      roomId: "room-sum",
      timestamp: "2026-09-20T10:00:05.000Z",
      speakerName: "RoxStar AI Sathi",
      speakerType: "ai",
      text: "Aur detail mein bhi samajh aa sakta hai",
      persona: "sathi",
      source: "ai",
    });

    const view = buildConversationSummary(store, "room-sum");
    expect(view.empty).toBe(false);
    expect(view.roomId).toBe("room-sum");
    expect(view.participants).toEqual(["Rahul"]);
    expect(view.humanTurns).toBe(1);
    expect(view.aiTurns).toBe(2);
    expect(view.dostTurns).toBe(1);
    expect(view.sathiTurns).toBe(1);
    expect(view.topicLines).toEqual(["AI kya hota hai?"]);
    expect(view.recentTurns).toHaveLength(3);
    expect(view.note.toLowerCase()).toContain("no llm");
  });

  it("does not invent topics beyond stored human text", () => {
    let store = emptyHistory();
    store = upsertHistoryMessage(store, {
      id: "h1",
      roomId: "r2",
      timestamp: "2026-09-20T11:00:00.000Z",
      speakerName: "Priya",
      speakerType: "human",
      text: "Cricket pasand hai",
      source: "text",
    });
    const view = buildConversationSummary(store);
    expect(view.topicLines).toEqual(["Cricket pasand hai"]);
    expect(view.topicLines.join(" ")).not.toMatch(/invented|summary of themes|key themes/i);
  });
});

describe("settingsInfo", () => {
  it("exposes backend/connection helpers and strips secrets", () => {
    expect(looksLikeSecretKey("api_key")).toBe(true);
    expect(looksLikeSecretKey("access_token")).toBe(true);
    expect(looksLikeSecretKey("livekit_configured")).toBe(false);

    const dirty = {
      status: "operational",
      api_key: "sk-secret-should-vanish",
      providers: {
        livekit_configured: true,
        sarvam_api_key: "abc",
        primary_provider: "gemini",
      },
      token: "lk_abcdefghijklmnopqrstuvwxyz012345",
    };
    const cleaned = sanitizeForDisplay(dirty) as Record<string, unknown>;
    expect(cleaned.api_key).toBeUndefined();
    expect(cleaned.token).toBeUndefined();
    expect((cleaned.providers as Record<string, unknown>).sarvam_api_key).toBeUndefined();
    expect((cleaned.providers as Record<string, unknown>).primary_provider).toBe("gemini");

    const safe = pickSafeSystemStatus({
      status: "operational",
      service: "roxstar-backend",
      version: "0.1.0",
      environment: "development",
      api_secret: "nope",
      providers: {
        livekit_configured: true,
        sarvam_configured: false,
        llm_configured: true,
        primary_provider: "gemini",
        fallback_provider: "nvidia",
        fallback_enabled: true,
        LIVEKIT_API_SECRET: "should-not-pass",
      },
    });
    expect(safe?.status).toBe("operational");
    expect(safe?.providers?.livekit_configured).toBe(true);
    expect(JSON.stringify(safe)).not.toMatch(/LIVEKIT_API_SECRET|should-not-pass|nope/i);
  });

  it("reads local data stats without inventing counts", () => {
    const map = new Map<string, string>();
    const storage = {
      getItem: (k: string) => (map.has(k) ? map.get(k)! : null),
    };
    expect(readLocalDataStats(storage)).toEqual({
      chatConversations: 0,
      chatMessages: 0,
      pipelineEvents: 0,
      scenarioResults: 0,
    });
    map.set(
      "roxstar-chat-history",
      JSON.stringify({
        version: 2,
        conversations: [
          {
            id: "r",
            roomId: "r",
            startedAt: "t",
            updatedAt: "t",
            participantNames: [],
            messageCount: 1,
            latestPreview: "",
            messages: [{ id: "1" }],
          },
        ],
      })
    );
    expect(readLocalDataStats(storage).chatConversations).toBe(1);
    expect(readLocalDataStats(storage).chatMessages).toBe(1);
  });
});

describe("app navigation routes", () => {
  it("keeps Documentation, Summary, and Settings routes valid", () => {
    expect(APP_NAV_ROUTES).toContain("/documentation");
    expect(APP_NAV_ROUTES).toContain("/tools/summary");
    expect(APP_NAV_ROUTES).toContain("/settings");
    expect(APP_NAV_ROUTES).not.toContain("https://github.com");
  });
});
