import { describe, expect, it } from "vitest";
import {
  ASSIGNMENT_SCENARIOS,
  evaluateAllScenarios,
  evaluateScenario,
  looksEnglishDominant,
  looksHinglishOrHindi,
  markScenarioRunning,
  resetAllScenarioStates,
  resetScenarioState,
  runScenarioEvaluation,
  type ScenarioId,
} from "./testScenarios";
import {
  type ChatHistoryMessage,
  type ChatHistoryStore,
  upsertHistoryMessage,
} from "./chatHistory";
import { type AnalyticsPipelineStore } from "./analytics";

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

function add(
  store: ChatHistoryStore,
  msg: ChatHistoryMessage
): ChatHistoryStore {
  return upsertHistoryMessage(store, msg);
}

describe("testScenarios — definitions", () => {
  it("defines all 7 assignment scenarios with required fields", () => {
    expect(ASSIGNMENT_SCENARIOS).toHaveLength(7);
    const ids = ASSIGNMENT_SCENARIOS.map((s) => s.id);
    expect(ids).toEqual([
      "hinglish-basic",
      "english-question",
      "multi-turn-context",
      "multi-user-context",
      "speaker-memory",
      "barge-in",
      "explicit-two-bot",
    ]);
    for (const s of ASSIGNMENT_SCENARIOS) {
      expect(s.name.length).toBeGreaterThan(0);
      expect(s.purpose.length).toBeGreaterThan(0);
      expect(s.steps.length).toBeGreaterThan(0);
      expect(s.expected.length).toBeGreaterThan(0);
      expect(s.roomId.startsWith("roxstar-scen-")).toBe(true);
      expect(s.prompts.length).toBeGreaterThan(0);
      expect(["interactive", "manual"]).toContain(s.execution);
    }
    expect(ASSIGNMENT_SCENARIOS.find((s) => s.id === "multi-user-context")?.execution).toBe(
      "manual"
    );
    expect(ASSIGNMENT_SCENARIOS.find((s) => s.id === "barge-in")?.execution).toBe("manual");
  });
});

describe("testScenarios — language helpers", () => {
  it("detects Hindi/Hinglish vs English-dominant", () => {
    expect(looksHinglishOrHindi("AI ek tarah ki buddhiman machine hai")).toBe(true);
    expect(looksHinglishOrHindi("यह एक उदाहरण है")).toBe(true);
    expect(looksEnglishDominant("Cloud computing is the delivery of computing services over the internet.")).toBe(
      true
    );
    expect(
      looksEnglishDominant("Cloud computing matlab internet pe services use karna hai.")
    ).toBe(false);
  });
});

describe("testScenarios — evaluation", () => {
  it("FAIL when expected routing/context is absent", () => {
    const empty = evaluateScenario("explicit-two-bot", emptyHistory());
    expect(empty.status).toBe("FAIL");
    expect(empty.checks.every((c) => c.ok)).toBe(false);

    let store = emptyHistory();
    store = add(store, {
      id: "h1",
      roomId: "roxstar-scen-routing",
      timestamp: "2026-09-20T10:00:00.000Z",
      speakerName: "Rahul",
      speakerType: "human",
      text: "AI Dost, tum batao.",
      source: "text",
      shouldRespond: true,
      selectedBot: "SATHI",
    });
    store = add(store, {
      id: "a1",
      roomId: "roxstar-scen-routing",
      timestamp: "2026-09-20T10:00:01.000Z",
      speakerName: "RoxStar AI Sathi",
      speakerType: "ai",
      text: "Haan bolo",
      persona: "sathi",
      source: "ai",
    });
    const wrong = evaluateScenario("explicit-two-bot", store);
    expect(wrong.status).toBe("FAIL");
    expect(wrong.checks.find((c) => c.id === "dost-route")?.ok).toBe(false);
  });

  it("PASS only when conditions are satisfied", () => {
    let store = emptyHistory();
    store = add(store, {
      id: "h1",
      roomId: "roxstar-scen-hinglish",
      timestamp: "2026-09-20T10:00:00.000Z",
      speakerName: "Rahul",
      speakerType: "human",
      text: "AI kya hota hai?",
      source: "voice",
      shouldRespond: true,
      selectedBot: "DOST",
    });
    store = add(store, {
      id: "a1",
      roomId: "roxstar-scen-hinglish",
      timestamp: "2026-09-20T10:00:02.000Z",
      speakerName: "RoxStar AI Dost",
      speakerType: "ai",
      text: "AI matlab artificial intelligence hai jo problems solve karti hai.",
      persona: "dost",
      source: "ai",
    });
    const pass = evaluateScenario("hinglish-basic", store);
    expect(pass.status).toBe("PASS");
    expect(pass.checks.every((c) => c.ok)).toBe(true);

    // Missing AI reply → FAIL
    let incomplete = emptyHistory();
    incomplete = add(incomplete, {
      id: "h2",
      roomId: "roxstar-scen-hinglish",
      timestamp: "2026-09-20T10:00:00.000Z",
      speakerName: "Rahul",
      speakerType: "human",
      text: "AI kya hota hai?",
      source: "voice",
      shouldRespond: true,
      selectedBot: "DOST",
    });
    expect(evaluateScenario("hinglish-basic", incomplete).status).toBe("FAIL");
  });

  it("PASS explicit two-bot when both routes observed", () => {
    let store = emptyHistory();
    store = add(store, {
      id: "d-h",
      roomId: "roxstar-scen-routing",
      timestamp: "2026-09-20T10:00:00.000Z",
      speakerName: "Rahul",
      speakerType: "human",
      text: "AI Dost, tum batao.",
      source: "text",
      shouldRespond: true,
      selectedBot: "DOST",
    });
    store = add(store, {
      id: "d-a",
      roomId: "roxstar-scen-routing",
      timestamp: "2026-09-20T10:00:01.000Z",
      speakerName: "RoxStar AI Dost",
      speakerType: "ai",
      text: "Haan dost sun raha hoon",
      persona: "dost",
      source: "ai",
    });
    store = add(store, {
      id: "s-h",
      roomId: "roxstar-scen-routing",
      timestamp: "2026-09-20T10:00:02.000Z",
      speakerName: "Rahul",
      speakerType: "human",
      text: "AI Sathi, tum batao.",
      source: "text",
      shouldRespond: true,
      selectedBot: "SATHI",
    });
    store = add(store, {
      id: "s-a",
      roomId: "roxstar-scen-routing",
      timestamp: "2026-09-20T10:00:03.000Z",
      speakerName: "RoxStar AI Sathi",
      speakerType: "ai",
      text: "Haan sathi yahan hoon",
      persona: "sathi",
      source: "ai",
    });
    expect(evaluateScenario("explicit-two-bot", store).status).toBe("PASS");
  });

  it("manual/interactive barge-in is not falsely marked PASS without cancel evidence", () => {
    let store = emptyHistory();
    store = add(store, {
      id: "h1",
      roomId: "roxstar-scen-bargein",
      timestamp: "2026-09-20T10:00:00.000Z",
      speakerName: "Rahul",
      speakerType: "human",
      text: "Detail mein samjhao",
      source: "voice",
    });
    store = add(store, {
      id: "h2",
      roomId: "roxstar-scen-bargein",
      timestamp: "2026-09-20T10:00:05.000Z",
      speakerName: "Rahul",
      speakerType: "human",
      text: "Ruko — short mein batao",
      source: "voice",
    });
    const emptyPipe: AnalyticsPipelineStore = { version: 1, events: [] };
    const noCancel = evaluateScenario("barge-in", store, emptyPipe);
    expect(noCancel.status).toBe("FAIL");
    expect(noCancel.checks.find((c) => c.id === "cancel-evidence")?.ok).toBe(false);
  });

  it("multi-user FAIL when cricket attributed to Priya", () => {
    let store = emptyHistory();
    store = add(store, {
      id: "r1",
      roomId: "roxstar-scen-multiuser",
      timestamp: "2026-09-20T10:00:00.000Z",
      speakerName: "Rahul",
      speakerType: "human",
      text: "Mera naam Rahul hai aur mujhe cricket pasand hai.",
      source: "voice",
    });
    store = add(store, {
      id: "p1",
      roomId: "roxstar-scen-multiuser",
      timestamp: "2026-09-20T10:00:05.000Z",
      speakerName: "Priya",
      speakerType: "human",
      text: "Rahul ne mujhe kya bataya tha?",
      source: "text",
    });
    store = add(store, {
      id: "a1",
      roomId: "roxstar-scen-multiuser",
      timestamp: "2026-09-20T10:00:06.000Z",
      speakerName: "RoxStar AI Dost",
      speakerType: "ai",
      text: "Priya, tumhe cricket pasand hai.",
      persona: "dost",
      source: "ai",
    });
    const bad = evaluateScenario("multi-user-context", store);
    expect(bad.status).toBe("FAIL");
  });

  it("scenario state reset clears PASS/FAIL", () => {
    const storage = memoryStorage();
    // Seed a passing hinglish session into chat history via evaluation path
    let hist = emptyHistory();
    hist = add(hist, {
      id: "h1",
      roomId: "roxstar-scen-hinglish",
      timestamp: "2026-09-20T10:00:00.000Z",
      speakerName: "Rahul",
      speakerType: "human",
      text: "AI kya hota hai?",
      source: "voice",
      shouldRespond: true,
      selectedBot: "DOST",
    });
    hist = add(hist, {
      id: "a1",
      roomId: "roxstar-scen-hinglish",
      timestamp: "2026-09-20T10:00:01.000Z",
      speakerName: "RoxStar AI Dost",
      speakerType: "ai",
      text: "AI ek smart system hai",
      persona: "dost",
      source: "ai",
    });
    storage.setItem("roxstar-chat-history", JSON.stringify(hist));

    const passed = runScenarioEvaluation("hinglish-basic", storage);
    expect(passed.status).toBe("PASS");

    const reset = resetScenarioState("hinglish-basic", storage);
    expect(reset.byId["hinglish-basic"]?.status).toBe("NOT_RUN");
    expect(reset.byId["hinglish-basic"]?.observed).toBe("");

    markScenarioRunning("barge-in", storage);
    const all = resetAllScenarioStates(storage);
    expect(all.byId["barge-in"]).toBeUndefined();
    expect(Object.keys(all.byId)).toHaveLength(0);
  });

  it("Evaluate All never invents PASS for empty local data", () => {
    const storage = memoryStorage();
    const store = evaluateAllScenarios(storage);
    const ids = ASSIGNMENT_SCENARIOS.map((s) => s.id) as ScenarioId[];
    for (const id of ids) {
      expect(store.byId[id]?.status).toBe("FAIL");
    }
  });
});
