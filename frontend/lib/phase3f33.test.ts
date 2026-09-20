import { describe, expect, it } from "vitest";
import {
  applyCanonicalAiResponse,
  applyStreamingChunk,
} from "../lib/streamingPreviewState";
import {
  buildParticipantGridEntries,
  classifyLiveKitParticipant,
} from "../lib/participantClassification";

describe("streamingPreviewState — Issue 1 stale generating cleanup", () => {
  it("clears matching preview when canonical response arrives", () => {
    const completed = new Set<string>();
    const chunked = applyStreamingChunk(null, completed, {
      requestId: "req-1",
      bot: "SATHI",
      textDelta: "Zaroor Priya",
    });
    expect(chunked.preview?.text).toBe("Zaroor Priya");
    expect(chunked.generatingBot).toBe("SATHI");

    const final = applyCanonicalAiResponse(chunked.preview, completed, {
      requestId: "req-1",
      bot: "SATHI",
      text: "Zaroor Priya! Cricket fact...",
    });
    expect(final.preview).toBeNull();
    expect(final.clearGenerating).toBe(true);
    expect(final.generatingBot).toBeNull();
    expect(final.completedRequestIds.has("req-1")).toBe(true);
  });

  it("ignores late chunks after canonical response for same requestId", () => {
    const completed = new Set<string>(["req-1"]);
    const late = applyStreamingChunk(
      null,
      completed,
      { requestId: "req-1", bot: "SATHI", textDelta: " late" }
    );
    expect(late.ignored).toBe(true);
    expect(late.preview).toBeNull();
  });

  it("does not clear another AI's active preview", () => {
    const dostPreview = {
      requestId: "req-dost",
      bot: "DOST" as const,
      botDisplayName: "RoxStar AI Dost",
      text: "Haan bhai",
      isFinal: false,
    };
    const result = applyCanonicalAiResponse(dostPreview, new Set(), {
      requestId: "req-sathi",
      bot: "SATHI",
      text: "Zaroor Priya",
    });
    expect(result.preview).toEqual(dostPreview);
    expect(result.clearGenerating).toBe(false);
    expect(result.generatingBot).toBe("DOST");
    expect(result.completedRequestIds.has("req-sathi")).toBe(true);
  });
});

describe("participantClassification — Issue 3 AI identity", () => {
  it("classifies ai_dost / ai_sathi as AI agents", () => {
    const dost = classifyLiveKitParticipant({
      identity: "ai_dost",
      name: "Roxstar AI Dost",
      kind: "agent",
    });
    expect(dost.role).toBe("AI_AGENT");
    expect(dost.personaId).toBe("dost");
    expect(dost.badgeText).toBe("AI Dost");

    const sathi = classifyLiveKitParticipant({
      identity: "ai_sathi",
      name: "Roxstar AI Sathi",
    });
    expect(sathi.role).toBe("AI_AGENT");
    expect(sathi.personaId).toBe("sathi");
    expect(sathi.badgeText).toBe("AI Sathi");
  });

  it("classifies Rahul / Priya as humans", () => {
    const rahul = classifyLiveKitParticipant({
      identity: "human-abc",
      name: "Rahul",
      isLocal: true,
    });
    expect(rahul.role).toBe("HUMAN");
    expect(rahul.badgeText).toBe("You (Human)");

    const priya = classifyLiveKitParticipant({
      identity: "human-xyz",
      name: "Priya",
    });
    expect(priya.role).toBe("HUMAN");
    expect(priya.badgeText).toBe("Human Participant");
  });

  it("does not duplicate AI placeholders when live AI present", () => {
    const live = [
      { id: "human-1", role: "HUMAN" },
      { id: "ai_dost", role: "AI_AGENT", personaId: "dost" },
      { id: "ai_sathi", role: "AI_AGENT", personaId: "sathi" },
    ];
    const placeholders = [
      { id: "roxstar-dost", role: "AI_AGENT", personaId: "dost" },
      { id: "roxstar-sathi", role: "AI_AGENT", personaId: "sathi" },
    ];
    const grid = buildParticipantGridEntries(live, placeholders);
    expect(grid.humanCount).toBe(1);
    expect(grid.ai.map((p) => p.id)).toEqual(["ai_dost", "ai_sathi"]);
  });
});
