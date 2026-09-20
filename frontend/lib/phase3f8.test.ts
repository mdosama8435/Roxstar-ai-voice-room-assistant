import { describe, expect, it } from "vitest";
import { APP_NAV_ROUTES } from "./settingsInfo";
import { DOC_SECTION_IDS, getDocumentationSectionIds } from "./documentationContent";
import { buildParticipantGridEntries } from "./participantClassification";
import { applyCanonicalAiResponse, applyStreamingChunk } from "./streamingPreviewState";

describe("phase3f8 polish — navigation & regression guards", () => {
  it("keeps all primary app routes wired", () => {
    for (const route of [
      "/room/demo",
      "/create-room",
      "/join-room",
      "/chat-history",
      "/analytics",
      "/documentation",
      "/tools/summary",
      "/tools/scenarios",
      "/settings",
    ]) {
      expect(APP_NAV_ROUTES).toContain(route);
    }
  });

  it("documentation covers STT / turn / LLM / TTS scan sections", () => {
    const ids = getDocumentationSectionIds();
    for (const id of ["stt", "turn-detection", "llm", "tts", "routing", "barge-in"] as const) {
      expect(ids).toContain(id);
      expect(DOC_SECTION_IDS).toContain(id);
    }
  });

  it("does not duplicate AI persona cards when live AI joins", () => {
    const live = [
      { id: "ai_dost", role: "AI_AGENT", personaId: "dost" },
      { id: "human-1", role: "HUMAN" },
    ];
    const placeholders = [
      { id: "roxstar-dost", role: "AI_AGENT", personaId: "dost" },
      { id: "roxstar-sathi", role: "AI_AGENT", personaId: "sathi" },
    ];
    const { humans, ai, humanCount } = buildParticipantGridEntries(live, placeholders);
    expect(humanCount).toBe(1);
    expect(humans).toHaveLength(1);
    expect(ai.filter((p) => p.personaId === "dost")).toHaveLength(1);
    expect(ai.some((p) => p.personaId === "sathi")).toBe(true);
  });

  it("preserves stale-generating guard after canonical AI response", () => {
    const completed = new Set<string>();
    const chunked = applyStreamingChunk(null, completed, {
      requestId: "req-1",
      bot: "DOST",
      textDelta: "Namaste",
    });
    const final = applyCanonicalAiResponse(chunked.preview, completed, {
      requestId: "req-1",
      bot: "DOST",
      text: "Namaste!",
    });
    expect(final.clearGenerating).toBe(true);
    const late = applyStreamingChunk(final.preview, final.completedRequestIds, {
      requestId: "req-1",
      bot: "DOST",
      textDelta: " late",
    });
    expect(late.ignored).toBe(true);
  });
});
