/**
 * In-app documentation sections for assignment/demo.
 * Content is grounded in existing README/docs — not invented runtime claims.
 */

export type DocLink = { href: string; label: string; external?: boolean };

export type DocSection = {
  id: string;
  title: string;
  paragraphs: string[];
  links?: DocLink[];
};

/** Ordered section ids — used by the page and tests. */
export const DOC_SECTION_IDS = [
  "overview",
  "architecture",
  "livekit-flow",
  "stt",
  "turn-detection",
  "routing",
  "multi-user-memory",
  "llm",
  "tts",
  "ai-dost",
  "ai-sathi",
  "barge-in",
  "providers",
  "failure-handling",
  "privacy",
  "testing",
  "limitations",
] as const;

export type DocSectionId = (typeof DOC_SECTION_IDS)[number];

export const DOCUMENTATION_SECTIONS: DocSection[] = [
  {
    id: "overview",
    title: "Project Overview",
    paragraphs: [
      "RoxStar AI Voice Room Assistant is a multi-user real-time voice and text room with two AI personas — RoxStar AI Dost and RoxStar AI Sathi — over LiveKit WebRTC.",
      "Humans can speak or type in Hindi, Roman Hinglish, or English. The backend orchestrates eligibility, routing, context/memory, LLM replies, and TTS while keeping a single-bot speech mutex.",
    ],
    links: [
      { href: "/room/demo", label: "Voice Room" },
      { href: "/create-room", label: "Create Room" },
    ],
  },
  {
    id: "architecture",
    title: "Architecture",
    paragraphs: [
      "Three tiers: Next.js frontend (LiveKit client + UI), FastAPI backend (tokens, STT gateway, orchestration, TTS publish), and agent/provider abstractions for STT, LLM, and TTS.",
      "Shared contracts (turns, eligibility, routing, transcripts) keep the media plane and control plane aligned without putting secrets in the browser.",
    ],
    links: [
      { href: "/settings", label: "Settings / health" },
      { href: "/analytics", label: "Analytics" },
    ],
  },
  {
    id: "livekit-flow",
    title: "LiveKit room flow",
    paragraphs: [
      "Client requests POST /api/v1/livekit/token with room name + display name. Backend returns a scoped LiveKit JWT plus an STT session token; API secrets never leave the server.",
      "Participant identities are opaque (e.g. human-<id>). The client connects to the SFU, publishes mic audio, subscribes to remote tracks, and uses DataChannel for chat, transcripts, orchestration, and AI text events.",
    ],
    links: [{ href: "/join-room", label: "Join Room" }],
  },
  {
    id: "stt",
    title: "STT",
    paragraphs: [
      "Browser AudioWorklet resamples mic audio and streams PCM to the FastAPI STT WebSocket gateway.",
      "When Sarvam is configured, Saaras realtime returns partial/final transcripts; finals are shown locally and can be broadcast on the LiveKit DataChannel.",
    ],
  },
  {
    id: "turn-detection",
    title: "Turn Detection",
    paragraphs: [
      "Streaming partials update an in-progress turn; finals commit a ConversationTurn keyed by room + participant.",
      "Pause/incomplete heuristics reduce premature AI replies on trailing conjunctions, ellipsis, or unfinished phrases.",
    ],
  },
  {
    id: "routing",
    title: "Turn routing",
    paragraphs: [
      "Eligibility decides whether any AI should speak (questions, requests, explicit address, follow-ups vs acknowledgements, casual statements, incomplete utterances).",
      "The router always picks exactly one of DOST, SATHI, or NONE — never both bots at once. A room-scoped turn lock enforces the single-speaker invariant.",
    ],
    links: [{ href: "/tools/scenarios", label: "Test Scenarios" }],
  },
  {
    id: "multi-user-memory",
    title: "Context / Memory",
    paragraphs: [
      "Room context keeps bounded recent turns and per-speaker profiles so facts stay attributed to the speaker who said them.",
      "Follow-ups (e.g. “Unki…”, “Maine tumhe kya bataya tha?”) can resolve against prior room/speaker context when the orchestrator has that history for the room.",
    ],
    links: [{ href: "/chat-history", label: "Chat History" }],
  },
  {
    id: "llm",
    title: "LLM",
    paragraphs: [
      "Eligible locked turns request a response from the configured primary LLM provider, with optional controlled fallback for retryable failures.",
      "Streaming chunks update the UI preview; the canonical final response clears generating state so late chunks cannot resurrect “AI Generating…”.",
    ],
  },
  {
    id: "tts",
    title: "TTS",
    paragraphs: [
      "Selected bot speech is synthesized (Sarvam Bulbul when configured) and published on the AI participant LiveKit audio track.",
      "Barge-in cancels active TTS so late audio does not overlap a new human turn.",
    ],
  },
  {
    id: "ai-dost",
    title: "AI Dost persona",
    paragraphs: [
      "Friendly, brotherly Hindi/Hinglish companion (warm, practical, light banter).",
      "Preferred for casual/tech-leaning turns when explicitly addressed as Dost / AI Dost, or when routing heuristics select DOST.",
    ],
  },
  {
    id: "ai-sathi",
    title: "AI Sathi persona",
    paragraphs: [
      "Empathetic, articulate guide persona with polished conversational Hindi/Hinglish.",
      "Selected when explicitly addressed as Sathi / AI Sathi, or when routing heuristics choose SATHI.",
    ],
  },
  {
    id: "barge-in",
    title: "Interruption / barge-in",
    paragraphs: [
      "A meaningful new human turn can cancel active LLM generation and clear/cancel TTS so late chunks do not keep publishing over the new turn.",
      "Casual ambient STT and incomplete utterances are designed not to barge-in; acknowledgements may soft-stop speech without starting a new AI reply.",
    ],
  },
  {
    id: "providers",
    title: "Provider configuration",
    paragraphs: [
      "Configured on the backend via environment variables (LiveKit, Sarvam STT/TTS, LLM primary/fallback). The frontend only needs NEXT_PUBLIC_BACKEND_URL.",
      "System status exposes whether providers are configured (boolean flags and provider names) — never API keys or tokens.",
    ],
    links: [{ href: "/settings", label: "View configuration status" }],
  },
  {
    id: "failure-handling",
    title: "Failure handling",
    paragraphs: [
      "Provider failures should not tear down the LiveKit room. Token/STT/LLM/TTS errors surface in the room event log and UI status chips.",
      "LLM path supports a controlled fallback provider for retryable failures (rate limit / quota / unavailable) when enabled in backend config.",
    ],
  },
  {
    id: "privacy",
    title: "Privacy / data handling",
    paragraphs: [
      "Browser stores completed chat turns, analytics pipeline event ids, and scenario results in localStorage — not raw audio, not API keys, not LiveKit/STT access tokens.",
      "Backend structured logs scrub sensitive fields. Prefer opaque participant identities on the media plane.",
    ],
    links: [{ href: "/settings", label: "Clear local data" }],
  },
  {
    id: "testing",
    title: "Testing",
    paragraphs: [
      "Frontend Vitest covers chat history, analytics aggregation, test-scenario evaluation, and related helpers. Backend/agents use Pytest for orchestration and provider contracts.",
      "The Test Scenarios page evaluates assignment flows against real local session evidence — PASS only when expected conditions are observed.",
    ],
    links: [{ href: "/tools/scenarios", label: "Test Scenarios" }],
  },
  {
    id: "limitations",
    title: "Known limitations",
    paragraphs: [
      "Chat history, analytics, and scenario results are per-browser localStorage (not a shared server database).",
      "Settings cannot show live LiveKit/STT state unless you are on the Voice Room page (provider is room-scoped).",
      "Barge-in PASS on Test Scenarios requires observed cancel/interrupt evidence in local pipeline data; mic barge-in remains a manual interactive check.",
      "Summary is deterministic from stored turns — it does not call an LLM to invent topics.",
    ],
  },
];

export function getDocumentationSections(): DocSection[] {
  return DOCUMENTATION_SECTIONS;
}

export function getDocumentationSectionIds(): string[] {
  return DOCUMENTATION_SECTIONS.map((s) => s.id);
}
