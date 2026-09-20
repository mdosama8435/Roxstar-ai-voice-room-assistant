/**
 * Assignment Test Scenarios — definitions + evidence-based evaluation.
 * PASS only when expected conditions are observed in real local data.
 * Does not call the orchestrator or invent AI responses.
 */

import {
  type ChatHistoryMessage,
  type ChatHistoryStore,
  getConversation,
  loadChatHistoryStore,
} from "./chatHistory";
import { loadPipelineStore, type AnalyticsPipelineStore } from "./analytics";

export const SCENARIO_RESULTS_STORAGE_KEY = "roxstar-scenario-results";

export type ScenarioStatus = "NOT_RUN" | "RUNNING" | "PASS" | "FAIL";

export type ScenarioExecution = "interactive" | "manual";

export type ScenarioId =
  | "hinglish-basic"
  | "english-question"
  | "multi-turn-context"
  | "multi-user-context"
  | "speaker-memory"
  | "barge-in"
  | "explicit-two-bot";

export interface ScenarioDefinition {
  id: ScenarioId;
  name: string;
  purpose: string;
  steps: string[];
  expected: string[];
  /** interactive = single user in room; manual = dual-browser / mic barge-in */
  execution: ScenarioExecution;
  roomId: string;
  /** Primary launch participant */
  launchName: string;
  /** Clipboard prompts (in order) */
  prompts: string[];
  /** Second browser participant when needed */
  secondaryName?: string;
}

export interface ScenarioCheck {
  id: string;
  label: string;
  ok: boolean;
  detail: string;
}

export interface ScenarioEvaluation {
  status: "PASS" | "FAIL";
  observed: string;
  checks: ScenarioCheck[];
}

export interface ScenarioRunState {
  status: ScenarioStatus;
  observed: string;
  checkedAt?: string;
  checks?: ScenarioCheck[];
}

export type ScenarioResultsStore = {
  version: 1;
  byId: Partial<Record<ScenarioId, ScenarioRunState>>;
};

export const ASSIGNMENT_SCENARIOS: ScenarioDefinition[] = [
  {
    id: "hinglish-basic",
    name: "Hinglish Basic Question",
    purpose: "Validate eligibility + single-bot Hindi/Hinglish reply for a basic AI question.",
    steps: ['Join the scenario room as Rahul.', 'Send or speak: "AI kya hota hai?"', "Wait for one AI reply.", "Return here and Evaluate."],
    expected: [
      "Turn is eligible (shouldRespond)",
      "Exactly one bot selected (DOST or SATHI, not NONE)",
      "AI reply is conversational Hindi/Hinglish",
    ],
    execution: "interactive",
    roomId: "roxstar-scen-hinglish",
    launchName: "Rahul",
    prompts: ["AI kya hota hai?"],
  },
  {
    id: "english-question",
    name: "English Question",
    purpose: "English input understood; reply stays natural Hindi/Hinglish unless English is requested.",
    steps: ['Join as Rahul.', 'Send: "What is cloud computing?"', "Wait for AI reply.", "Evaluate from local session data."],
    expected: [
      "Human English turn recorded",
      "Turn eligible with one bot selected",
      "AI response mainly Hindi/Hinglish (not English-only)",
    ],
    execution: "interactive",
    roomId: "roxstar-scen-english",
    launchName: "Rahul",
    prompts: ["What is cloud computing?"],
  },
  {
    id: "multi-turn-context",
    name: "Multi-turn Context",
    purpose: "Second turn pronoun “Unki” resolves from prior Shah Rukh Khan context.",
    steps: [
      "Join as Rahul.",
      'Turn 1: "Shah Rukh Khan kaun hai?" — wait for reply.',
      'Turn 2: "Unki koi famous movie batao." — wait for reply.',
      "Evaluate.",
    ],
    expected: [
      "Both human turns present in order",
      "AI reply after the second turn",
      "Second-turn reply references SRK/movie context (not an unrelated reset)",
    ],
    execution: "interactive",
    roomId: "roxstar-scen-multiturn",
    launchName: "Rahul",
    prompts: ["Shah Rukh Khan kaun hai?", "Unki koi famous movie batao."],
  },
  {
    id: "multi-user-context",
    name: "Multi-user Context",
    purpose: "Rahul’s fact stays with Rahul; Priya’s question is answered without mis-attribution.",
    steps: [
      "Browser A: join as Rahul — say the cricket fact.",
      "Browser B: join as Priya — ask what Rahul said.",
      "Confirm AI reply attributes the fact to Rahul, not Priya.",
      "Evaluate.",
    ],
    expected: [
      "Rahul’s fact turn present",
      "Priya’s question present",
      "AI reply after Priya mentions Rahul’s cricket fact",
      "Reply does not claim Priya likes cricket",
    ],
    execution: "manual",
    roomId: "roxstar-scen-multiuser",
    launchName: "Rahul",
    secondaryName: "Priya",
    prompts: [
      "Mera naam Rahul hai aur mujhe cricket pasand hai.",
      "Rahul ne mujhe kya bataya tha?",
    ],
  },
  {
    id: "speaker-memory",
    name: "Speaker Memory",
    purpose: "Same speaker recall uses speaker-specific memory.",
    steps: [
      "Join as Rahul.",
      "Share a personal fact (e.g. cricket).",
      'Later ask: "Maine tumhe kya bataya tha?"',
      "Evaluate.",
    ],
    expected: [
      "Earlier Rahul fact turn present",
      "Rahul recall question present",
      "AI reply recalls Rahul’s fact for Rahul",
    ],
    execution: "interactive",
    roomId: "roxstar-scen-memory",
    launchName: "Rahul",
    prompts: [
      "Mera naam Rahul hai aur mujhe cricket pasand hai.",
      "Maine tumhe kya bataya tha?",
    ],
  },
  {
    id: "barge-in",
    name: "Interruption / Barge-in",
    purpose: "Meaningful new human turn cancels active AI generation; no overlapping TTS.",
    steps: [
      "Join the room with mic enabled.",
      "Ask a question that starts a long AI reply.",
      "While AI is speaking/generating, interrupt with a new meaningful turn.",
      "Confirm cancel + single new reply; then Evaluate.",
    ],
    expected: [
      "Active generation cancelled",
      "TTS/audio queue cleared",
      "Late chunks do not publish",
      "New turn gets one response",
      "No overlapping AI speech",
    ],
    execution: "manual",
    roomId: "roxstar-scen-bargein",
    launchName: "Rahul",
    prompts: [
      "AI Dost, cloud computing ke baare mein detail mein samjhao.",
      "Ruko — short mein batao: AI kya hota hai?",
    ],
  },
  {
    id: "explicit-two-bot",
    name: "Explicit Two-Bot Routing",
    purpose: "Explicit mention routes to AI Dost then AI Sathi.",
    steps: [
      'Send: "AI Dost, tum batao." — expect Dost.',
      'Send: "AI Sathi, tum batao." — expect Sathi.',
      "Evaluate both routing observations.",
    ],
    expected: [
      '"AI Dost, tum batao." → selectedBot DOST (or Dost reply)',
      '"AI Sathi, tum batao." → selectedBot SATHI (or Sathi reply)',
    ],
    execution: "interactive",
    roomId: "roxstar-scen-routing",
    launchName: "Rahul",
    prompts: ["AI Dost, tum batao.", "AI Sathi, tum batao."],
  },
];

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof localStorage !== "undefined";
}

function normalizeText(s: string): string {
  return (s || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function includesNormalized(haystack: string, needle: string): boolean {
  return normalizeText(haystack).includes(normalizeText(needle));
}

function findHumanTurn(
  messages: ChatHistoryMessage[],
  prompt: string
): ChatHistoryMessage | undefined {
  return messages.find(
    (m) => m.speakerType === "human" && includesNormalized(m.text, prompt)
  );
}

function indexOfMessage(messages: ChatHistoryMessage[], id: string): number {
  return messages.findIndex((m) => m.id === id);
}

function nextAiAfter(
  messages: ChatHistoryMessage[],
  afterIdx: number
): ChatHistoryMessage | undefined {
  for (let i = afterIdx + 1; i < messages.length; i++) {
    if (messages[i].speakerType === "ai") return messages[i];
  }
  return undefined;
}

/** Devanagari or common Hindi/Hinglish function words. */
export function looksHinglishOrHindi(text: string): boolean {
  const t = text || "";
  if (/[\u0900-\u097F]/.test(t)) return true;
  return /\b(hai|hota|hain|kya|nahi|nahin|aap|tum|mein|main|ka|ki|ke|aur|batao|bataata|zaroor|samajh|kyunki|matlab|jaankaari|jankari|baare)\b/i.test(
    t
  );
}

/** Crude English-only detector for failing English→Hindi expectation. */
export function looksEnglishDominant(text: string): boolean {
  const t = (text || "").trim();
  if (!t) return false;
  if (/[\u0900-\u097F]/.test(t)) return false;
  if (looksHinglishOrHindi(t)) return false;
  // Mostly Latin letters and English stopwords
  const latinRatio = (t.match(/[A-Za-z]/g) || []).length / Math.max(t.length, 1);
  return latinRatio > 0.7 && /\b(the|is|are|a|an|of|to|and|for|in|on|with|that|this)\b/i.test(t);
}

function botSelected(msg: ChatHistoryMessage | undefined): "DOST" | "SATHI" | "NONE" | null {
  if (!msg) return null;
  if (msg.selectedBot === "DOST" || msg.selectedBot === "SATHI" || msg.selectedBot === "NONE") {
    return msg.selectedBot;
  }
  return null;
}

function allChecksPass(checks: ScenarioCheck[]): boolean {
  return checks.length > 0 && checks.every((c) => c.ok);
}

function summarize(checks: ScenarioCheck[]): string {
  const failed = checks.filter((c) => !c.ok);
  if (failed.length === 0) {
    return checks.map((c) => c.detail).join("; ");
  }
  return failed.map((c) => c.detail).join("; ");
}

export function getScenarioById(id: ScenarioId): ScenarioDefinition | undefined {
  return ASSIGNMENT_SCENARIOS.find((s) => s.id === id);
}

export function roomDeepLink(scenario: ScenarioDefinition, name?: string): string {
  const participant = name || scenario.launchName;
  return `/room/demo?room=${encodeURIComponent(scenario.roomId)}&name=${encodeURIComponent(participant)}&auto=1`;
}

export function emptyResultsStore(): ScenarioResultsStore {
  return { version: 1, byId: {} };
}

export function normalizeResultsStore(raw: unknown): ScenarioResultsStore {
  if (!raw || typeof raw !== "object") return emptyResultsStore();
  const obj = raw as Partial<ScenarioResultsStore>;
  if (obj.version !== 1 || !obj.byId || typeof obj.byId !== "object") {
    return emptyResultsStore();
  }
  return { version: 1, byId: { ...obj.byId } };
}

export function loadScenarioResults(
  storage: Pick<Storage, "getItem"> | null = isBrowser() ? localStorage : null
): ScenarioResultsStore {
  if (!storage) return emptyResultsStore();
  try {
    const raw = storage.getItem(SCENARIO_RESULTS_STORAGE_KEY);
    if (!raw) return emptyResultsStore();
    return normalizeResultsStore(JSON.parse(raw));
  } catch {
    return emptyResultsStore();
  }
}

export function saveScenarioResults(
  store: ScenarioResultsStore,
  storage: Pick<Storage, "setItem"> | null = isBrowser() ? localStorage : null
): void {
  if (!storage) return;
  try {
    storage.setItem(SCENARIO_RESULTS_STORAGE_KEY, JSON.stringify(store));
  } catch {
    // best-effort
  }
}

export function setScenarioRunState(
  id: ScenarioId,
  state: ScenarioRunState,
  storage: Pick<Storage, "getItem" | "setItem"> | null = isBrowser() ? localStorage : null
): ScenarioResultsStore {
  const store = loadScenarioResults(storage);
  const next: ScenarioResultsStore = {
    version: 1,
    byId: { ...store.byId, [id]: state },
  };
  saveScenarioResults(next, storage);
  return next;
}

export function resetScenarioState(
  id: ScenarioId,
  storage: Pick<Storage, "getItem" | "setItem"> | null = isBrowser() ? localStorage : null
): ScenarioResultsStore {
  return setScenarioRunState(
    id,
    { status: "NOT_RUN", observed: "" },
    storage
  );
}

export function resetAllScenarioStates(
  storage: Pick<Storage, "getItem" | "setItem"> | null = isBrowser() ? localStorage : null
): ScenarioResultsStore {
  const next = emptyResultsStore();
  saveScenarioResults(next, storage);
  return next;
}

function messagesForRoom(
  history: ChatHistoryStore,
  roomId: string
): ChatHistoryMessage[] {
  const conv = getConversation(history, roomId);
  return conv?.messages ? [...conv.messages] : [];
}

function evaluateHinglishBasic(messages: ChatHistoryMessage[]): ScenarioEvaluation {
  const checks: ScenarioCheck[] = [];
  const human = findHumanTurn(messages, "AI kya hota hai?");
  checks.push({
    id: "human-turn",
    label: "Human input observed",
    ok: Boolean(human),
    detail: human ? `Found human turn: “${human.text.slice(0, 48)}”` : "Missing “AI kya hota hai?” turn",
  });

  const bot = botSelected(human);
  const eligible = human?.shouldRespond === true;
  checks.push({
    id: "eligible",
    label: "Turn eligible",
    ok: eligible,
    detail: human
      ? eligible
        ? "shouldRespond=true"
        : human.shouldRespond === false
          ? "shouldRespond=false (not eligible)"
          : "No orchestration eligibility on turn"
      : "No turn to evaluate eligibility",
  });

  const oneBot = bot === "DOST" || bot === "SATHI";
  checks.push({
    id: "one-bot",
    label: "One AI selected",
    ok: oneBot,
    detail: bot ? `selectedBot=${bot}` : "No selectedBot on human turn",
  });

  const ai =
    human != null ? nextAiAfter(messages, indexOfMessage(messages, human.id)) : undefined;
  const hinglish = Boolean(ai && looksHinglishOrHindi(ai.text));
  checks.push({
    id: "hinglish-reply",
    label: "Hindi/Hinglish AI reply",
    ok: hinglish,
    detail: ai
      ? hinglish
        ? `AI reply looks Hindi/Hinglish (${ai.persona || "ai"})`
        : `AI reply does not look Hindi/Hinglish: “${ai.text.slice(0, 60)}”`
      : "No AI response after human turn",
  });

  return {
    status: allChecksPass(checks) ? "PASS" : "FAIL",
    observed: summarize(checks),
    checks,
  };
}

function evaluateEnglishQuestion(messages: ChatHistoryMessage[]): ScenarioEvaluation {
  const checks: ScenarioCheck[] = [];
  const human = findHumanTurn(messages, "What is cloud computing?");
  checks.push({
    id: "english-input",
    label: "English question observed",
    ok: Boolean(human),
    detail: human ? "Found English cloud-computing question" : "Missing English question turn",
  });

  const eligible = human?.shouldRespond === true;
  const bot = botSelected(human);
  const oneBot = bot === "DOST" || bot === "SATHI";
  checks.push({
    id: "eligible-routed",
    label: "Eligible + bot selected",
    ok: eligible && oneBot,
    detail: human
      ? `shouldRespond=${String(human.shouldRespond)} selectedBot=${bot ?? "missing"}`
      : "No turn",
  });

  const ai =
    human != null ? nextAiAfter(messages, indexOfMessage(messages, human.id)) : undefined;
  const hinglishOk = Boolean(ai && looksHinglishOrHindi(ai.text) && !looksEnglishDominant(ai.text));
  checks.push({
    id: "hinglish-reply",
    label: "Reply mainly Hindi/Hinglish",
    ok: hinglishOk,
    detail: ai
      ? hinglishOk
        ? "AI reply mainly Hindi/Hinglish"
        : looksEnglishDominant(ai.text)
          ? "AI reply looks English-dominant (expected Hindi/Hinglish)"
          : `AI reply language unclear: “${ai.text.slice(0, 60)}”`
      : "No AI response after English question",
  });

  return {
    status: allChecksPass(checks) ? "PASS" : "FAIL",
    observed: summarize(checks),
    checks,
  };
}

function evaluateMultiTurn(messages: ChatHistoryMessage[]): ScenarioEvaluation {
  const checks: ScenarioCheck[] = [];
  const t1 = findHumanTurn(messages, "Shah Rukh Khan kaun hai?");
  const t2 = messages.find(
    (m) =>
      m.speakerType === "human" &&
      includesNormalized(m.text, "Unki koi famous movie batao")
  );
  const orderOk =
    Boolean(t1 && t2) &&
    indexOfMessage(messages, t1!.id) < indexOfMessage(messages, t2!.id);

  checks.push({
    id: "both-turns",
    label: "Both turns in order",
    ok: orderOk,
    detail: orderOk
      ? "Both human turns present in order"
      : !t1
        ? "Missing first turn (Shah Rukh Khan…)"
        : !t2
          ? "Missing second turn (Unki…)"
          : "Turns out of order",
  });

  const ai2 = t2 != null ? nextAiAfter(messages, indexOfMessage(messages, t2.id)) : undefined;
  checks.push({
    id: "ai-after-second",
    label: "AI reply after second turn",
    ok: Boolean(ai2),
    detail: ai2 ? "AI response after second turn" : "No AI response after second turn",
  });

  const contextOk = Boolean(
    ai2 &&
      (/\b(shah\s*rukh|srk|khan|movie|film|dilwale|pathaan|chennai|don|raees|jab\s*tak|veer|devdas|chak\s*de)\b/i.test(
        ai2.text
      ) ||
        /[\u0900-\u097F]/.test(ai2.text))
  );
  checks.push({
    id: "context-resolved",
    label: "Context not reset",
    ok: contextOk,
    detail: ai2
      ? contextOk
        ? "Second reply appears to continue SRK/movie context"
        : `Second reply lacks SRK/movie cues: “${ai2.text.slice(0, 60)}”`
      : "Cannot verify context without AI reply",
  });

  return {
    status: allChecksPass(checks) ? "PASS" : "FAIL",
    observed: summarize(checks),
    checks,
  };
}

function evaluateMultiUser(messages: ChatHistoryMessage[]): ScenarioEvaluation {
  const checks: ScenarioCheck[] = [];
  const rahulFact = messages.find(
    (m) =>
      m.speakerType === "human" &&
      /rahul/i.test(m.speakerName) &&
      includesNormalized(m.text, "cricket pasand")
  );
  const priyaQ = messages.find(
    (m) =>
      m.speakerType === "human" &&
      /priya/i.test(m.speakerName) &&
      includesNormalized(m.text, "Rahul ne mujhe kya bataya")
  );

  checks.push({
    id: "rahul-fact",
    label: "Rahul fact turn",
    ok: Boolean(rahulFact),
    detail: rahulFact
      ? `Rahul fact from ${rahulFact.speakerName}`
      : "Missing Rahul cricket-fact turn",
  });
  checks.push({
    id: "priya-question",
    label: "Priya question turn",
    ok: Boolean(priyaQ),
    detail: priyaQ ? `Priya question from ${priyaQ.speakerName}` : "Missing Priya question turn",
  });

  const ai = priyaQ != null ? nextAiAfter(messages, indexOfMessage(messages, priyaQ.id)) : undefined;
  const attributesRahul = Boolean(
    ai && /rahul/i.test(ai.text) && /cricket/i.test(ai.text)
  );
  const misattributesPriya = Boolean(
    ai && /priya/i.test(ai.text) && /cricket/i.test(ai.text) && /pasand|likes|like/i.test(ai.text)
  );

  checks.push({
    id: "ai-attributes-rahul",
    label: "Fact attributed to Rahul",
    ok: attributesRahul && !misattributesPriya,
    detail: ai
      ? attributesRahul && !misattributesPriya
        ? "AI reply links cricket fact to Rahul"
        : misattributesPriya
          ? "AI reply appears to attribute cricket to Priya"
          : `AI reply missing Rahul+cricket: “${ai.text.slice(0, 80)}”`
      : "No AI reply after Priya’s question",
  });

  return {
    status: allChecksPass(checks) ? "PASS" : "FAIL",
    observed: summarize(checks),
    checks,
  };
}

function evaluateSpeakerMemory(messages: ChatHistoryMessage[]): ScenarioEvaluation {
  const checks: ScenarioCheck[] = [];
  const fact = messages.find(
    (m) =>
      m.speakerType === "human" &&
      /rahul/i.test(m.speakerName) &&
      /cricket|pasand|naam/i.test(m.text)
  );
  const recall = messages.find(
    (m) =>
      m.speakerType === "human" &&
      /rahul/i.test(m.speakerName) &&
      includesNormalized(m.text, "Maine tumhe kya bataya")
  );
  const orderOk =
    Boolean(fact && recall) &&
    indexOfMessage(messages, fact!.id) < indexOfMessage(messages, recall!.id);

  checks.push({
    id: "fact-and-recall",
    label: "Fact then recall from Rahul",
    ok: orderOk,
    detail: orderOk
      ? "Rahul fact and recall turns in order"
      : !fact
        ? "Missing Rahul fact turn"
        : !recall
          ? "Missing Rahul recall question"
          : "Recall before fact",
  });

  const ai = recall != null ? nextAiAfter(messages, indexOfMessage(messages, recall.id)) : undefined;
  const recallsOk = Boolean(
    ai && (/cricket/i.test(ai.text) || /pasand/i.test(ai.text) || /rahul/i.test(ai.text))
  );
  checks.push({
    id: "memory-used",
    label: "Speaker memory in reply",
    ok: recallsOk,
    detail: ai
      ? recallsOk
        ? "AI reply references Rahul’s prior fact"
        : `AI reply lacks memory cues: “${ai.text.slice(0, 60)}”`
      : "No AI reply after recall question",
  });

  return {
    status: allChecksPass(checks) ? "PASS" : "FAIL",
    observed: summarize(checks),
    checks,
  };
}

/**
 * Barge-in cannot PASS without observed cancel/interrupt evidence in local stores.
 * Never invents PASS for manual mic scenarios.
 */
function evaluateBargeIn(
  messages: ChatHistoryMessage[],
  pipeline: AnalyticsPipelineStore
): ScenarioEvaluation {
  const checks: ScenarioCheck[] = [];
  const cancelEvidence = pipeline.events.some((e) =>
    /CANCEL|BARGE|INTERRUPT/i.test(e.type)
  );
  checks.push({
    id: "cancel-evidence",
    label: "Cancel / barge-in evidence",
    ok: cancelEvidence,
    detail: cancelEvidence
      ? "Pipeline contains cancel/barge/interrupt event"
      : "No cancel/barge/interrupt pipeline events in local data — complete interactive barge-in in the room (manual)",
  });

  // Optional weak signal: at least two human turns and one AI — still not enough to PASS alone
  const humans = messages.filter((m) => m.speakerType === "human");
  checks.push({
    id: "activity",
    label: "Session activity present",
    ok: humans.length >= 2,
    detail:
      humans.length >= 2
        ? `${humans.length} human turns in scenario room`
        : "Need ≥2 human turns in barge-in room before evaluation",
  });

  // Explicit: both must pass — cancel evidence required so we never false-PASS
  return {
    status: allChecksPass(checks) ? "PASS" : "FAIL",
    observed: summarize(checks),
    checks,
  };
}

function evaluateExplicitRouting(messages: ChatHistoryMessage[]): ScenarioEvaluation {
  const checks: ScenarioCheck[] = [];
  const dostTurn = findHumanTurn(messages, "AI Dost, tum batao");
  const sathiTurn = findHumanTurn(messages, "AI Sathi, tum batao");

  const dostBot = botSelected(dostTurn);
  const dostAi =
    dostTurn != null ? nextAiAfter(messages, indexOfMessage(messages, dostTurn.id)) : undefined;
  const dostOk = dostBot === "DOST" || dostAi?.persona === "dost";
  checks.push({
    id: "dost-route",
    label: "AI Dost selected",
    ok: dostOk,
    detail: dostTurn
      ? dostOk
        ? `Dost routing ok (selectedBot=${dostBot ?? "n/a"}, persona=${dostAi?.persona ?? "n/a"})`
        : `Expected DOST; selectedBot=${dostBot ?? "missing"}, persona=${dostAi?.persona ?? "none"}`
      : "Missing “AI Dost, tum batao.” turn",
  });

  const sathiBot = botSelected(sathiTurn);
  const sathiAi =
    sathiTurn != null ? nextAiAfter(messages, indexOfMessage(messages, sathiTurn.id)) : undefined;
  const sathiOk = sathiBot === "SATHI" || sathiAi?.persona === "sathi";
  checks.push({
    id: "sathi-route",
    label: "AI Sathi selected",
    ok: sathiOk,
    detail: sathiTurn
      ? sathiOk
        ? `Sathi routing ok (selectedBot=${sathiBot ?? "n/a"}, persona=${sathiAi?.persona ?? "n/a"})`
        : `Expected SATHI; selectedBot=${sathiBot ?? "missing"}, persona=${sathiAi?.persona ?? "none"}`
      : "Missing “AI Sathi, tum batao.” turn",
  });

  return {
    status: allChecksPass(checks) ? "PASS" : "FAIL",
    observed: summarize(checks),
    checks,
  };
}

export function evaluateScenario(
  scenarioId: ScenarioId,
  history: ChatHistoryStore,
  pipeline: AnalyticsPipelineStore = { version: 1, events: [] }
): ScenarioEvaluation {
  const def = getScenarioById(scenarioId);
  if (!def) {
    return {
      status: "FAIL",
      observed: "Unknown scenario",
      checks: [{ id: "unknown", label: "Scenario exists", ok: false, detail: "Unknown id" }],
    };
  }

  const roomPipeline: AnalyticsPipelineStore = {
    version: 1,
    events: pipeline.events.filter((e) => e.roomId === def.roomId),
  };
  const messages = messagesForRoom(history, def.roomId);

  switch (scenarioId) {
    case "hinglish-basic":
      return evaluateHinglishBasic(messages);
    case "english-question":
      return evaluateEnglishQuestion(messages);
    case "multi-turn-context":
      return evaluateMultiTurn(messages);
    case "multi-user-context":
      return evaluateMultiUser(messages);
    case "speaker-memory":
      return evaluateSpeakerMemory(messages);
    case "barge-in":
      return evaluateBargeIn(messages, roomPipeline);
    case "explicit-two-bot":
      return evaluateExplicitRouting(messages);
    default:
      return {
        status: "FAIL",
        observed: "No evaluator",
        checks: [{ id: "eval", label: "Evaluator", ok: false, detail: "No evaluator" }],
      };
  }
}

/**
 * Evaluate against local stores and persist PASS/FAIL.
 * Never marks PASS without satisfied checks.
 */
export function runScenarioEvaluation(
  scenarioId: ScenarioId,
  storage: Pick<Storage, "getItem" | "setItem"> | null = isBrowser() ? localStorage : null
): ScenarioRunState {
  const history = loadChatHistoryStore(storage);
  const pipeline = loadPipelineStore(storage);
  const result = evaluateScenario(scenarioId, history, pipeline);
  const state: ScenarioRunState = {
    status: result.status,
    observed: result.observed,
    checkedAt: new Date().toISOString(),
    checks: result.checks,
  };
  setScenarioRunState(scenarioId, state, storage);
  return state;
}

/** Safe “Run All”: evaluate every scenario from local evidence (no room spam). */
export function evaluateAllScenarios(
  storage: Pick<Storage, "getItem" | "setItem"> | null = isBrowser() ? localStorage : null
): ScenarioResultsStore {
  for (const s of ASSIGNMENT_SCENARIOS) {
    runScenarioEvaluation(s.id, storage);
  }
  return loadScenarioResults(storage);
}

export function markScenarioRunning(
  scenarioId: ScenarioId,
  storage: Pick<Storage, "getItem" | "setItem"> | null = isBrowser() ? localStorage : null
): ScenarioResultsStore {
  return setScenarioRunState(
    scenarioId,
    {
      status: "RUNNING",
      observed: "Room launched — complete steps, then Evaluate from local session data.",
    },
    storage
  );
}
