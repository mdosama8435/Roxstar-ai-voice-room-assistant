import { describe, expect, it } from "vitest";
import {
  applyTtsEvent,
  createInitialTtsPipelineState,
  formatTtsPipelineLabel,
  isTtsPipelineActive,
  selectPipelineTtsStatus,
} from "./ttsPipelineState";

describe("ttsPipelineState — Phase 3F.10.2 real event mapping", () => {
  it("tts.started -> generating", () => {
    const next = applyTtsEvent(createInitialTtsPipelineState(), {
      event_type: "tts.started",
      agent_id: "dost",
      request_id: "tts-1",
    });
    expect(next.dost).toBe("generating");
    expect(selectPipelineTtsStatus(next)).toBe("generating");
    expect(isTtsPipelineActive(next.dost)).toBe(true);
  });

  it("tts.first_audio -> publishing", () => {
    let state = applyTtsEvent(createInitialTtsPipelineState(), {
      event_type: "tts.started",
      agent_id: "sathi",
    });
    state = applyTtsEvent(state, {
      event_type: "tts.first_audio",
      agent_id: "sathi",
    });
    expect(state.sathi).toBe("publishing");
    expect(selectPipelineTtsStatus(state)).toBe("publishing");
  });

  it("completion -> idle/completed", () => {
    let state = applyTtsEvent(createInitialTtsPipelineState(), {
      event_type: "tts.started",
      agent_id: "dost",
    });
    state = applyTtsEvent(state, {
      event_type: "tts.first_audio",
      agent_id: "dost",
    });
    state = applyTtsEvent(state, {
      event_type: "tts.completed",
      agent_id: "dost",
    });
    expect(["idle", "completed"]).toContain(state.dost);
    expect(isTtsPipelineActive(state.dost)).toBe(false);
    expect(formatTtsPipelineLabel(state.dost, true)).not.toMatch(/GENERATING|PUBLISHING/);
  });

  it("audio.published also marks completion", () => {
    const next = applyTtsEvent(createInitialTtsPipelineState(), {
      event_type: "audio.published",
      agent_id: "dost",
    });
    expect(["idle", "completed"]).toContain(next.dost);
  });

  it("failure -> failed", () => {
    const next = applyTtsEvent(createInitialTtsPipelineState(), {
      event_type: "tts.failed",
      agent_id: "dost",
    });
    expect(next.dost).toBe("failed");
    expect(selectPipelineTtsStatus(next)).toBe("failed");
  });

  it("cancellation -> cancelled", () => {
    let state = applyTtsEvent(createInitialTtsPipelineState(), {
      event_type: "tts.started",
      agent_id: "sathi",
    });
    state = applyTtsEvent(state, {
      event_type: "tts.cancelled",
      agent_id: "sathi",
    });
    expect(state.sathi).toBe("cancelled");
  });

  it("unrelated bot events do not change another bot's TTS state", () => {
    let state = applyTtsEvent(createInitialTtsPipelineState(), {
      event_type: "tts.started",
      agent_id: "dost",
    });
    state = applyTtsEvent(state, {
      event_type: "tts.first_audio",
      agent_id: "dost",
    });
    expect(state.dost).toBe("publishing");
    expect(state.sathi).toBe("idle");

    state = applyTtsEvent(state, {
      event_type: "tts.started",
      agent_id: "sathi",
    });
    expect(state.dost).toBe("publishing");
    expect(state.sathi).toBe("generating");

    state = applyTtsEvent(state, {
      event_type: "tts.failed",
      agent_id: "sathi",
    });
    expect(state.dost).toBe("publishing");
    expect(state.sathi).toBe("failed");
  });

  it("ignores unknown event types and unknown agents", () => {
    const initial = createInitialTtsPipelineState();
    expect(
      applyTtsEvent(initial, { event_type: "llm.chunk", agent_id: "dost" })
    ).toEqual(initial);
    expect(
      applyTtsEvent(initial, { event_type: "tts.started", agent_id: "unknown" })
    ).toEqual(initial);
  });
});
