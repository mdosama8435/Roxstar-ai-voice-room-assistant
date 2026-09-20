/**
 * Deterministic conversation summary from chatHistory v2.
 * Never invents topics or calls an LLM.
 */

import {
  type ChatHistoryConversation,
  type ChatHistoryMessage,
  type ChatHistoryStore,
  getConversation,
  listConversations,
  loadChatHistoryStore,
} from "./chatHistory";
import { formatDuration } from "./analytics";

export type ConversationSummaryView = {
  empty: boolean;
  roomId: string | null;
  startedAt?: string;
  updatedAt?: string;
  durationLabel?: string;
  participants: string[];
  humanTurns: number;
  aiTurns: number;
  dostTurns: number;
  sathiTurns: number;
  /** Human message previews used as topic lines — only from stored text. */
  topicLines: string[];
  recentTurns: Array<{
    speakerName: string;
    speakerType: "human" | "ai";
    persona?: "dost" | "sathi";
    text: string;
    timestamp: string;
  }>;
  sessionCount: number;
  availableRooms: Array<{ roomId: string; messageCount: number; updatedAt: string }>;
  note: string;
};

const MAX_TOPIC_LINES = 8;
const MAX_RECENT = 12;

function durationLabel(startedAt: string, updatedAt: string): string | undefined {
  const a = Date.parse(startedAt);
  const b = Date.parse(updatedAt);
  if (!Number.isFinite(a) || !Number.isFinite(b) || b < a) return undefined;
  return formatDuration(b - a);
}

function summarizeConversation(conv: ChatHistoryConversation): ConversationSummaryView {
  const messages = conv.messages;
  let humanTurns = 0;
  let aiTurns = 0;
  let dostTurns = 0;
  let sathiTurns = 0;
  const topicLines: string[] = [];

  for (const m of messages) {
    if (m.speakerType === "human") {
      humanTurns += 1;
      if (topicLines.length < MAX_TOPIC_LINES) {
        const line = m.text.trim();
        if (line) topicLines.push(line.slice(0, 160) + (line.length > 160 ? "…" : ""));
      }
    } else {
      aiTurns += 1;
      if (m.persona === "dost") dostTurns += 1;
      else if (m.persona === "sathi") sathiTurns += 1;
    }
  }

  const recent = messages.slice(-MAX_RECENT).map((m: ChatHistoryMessage) => ({
    speakerName: m.speakerName,
    speakerType: m.speakerType,
    persona: m.persona,
    text: m.text,
    timestamp: m.timestamp,
  }));

  const dur = durationLabel(conv.startedAt, conv.updatedAt);

  return {
    empty: false,
    roomId: conv.roomId,
    startedAt: conv.startedAt,
    updatedAt: conv.updatedAt,
    durationLabel: dur,
    participants: [...conv.participantNames],
    humanTurns,
    aiTurns,
    dostTurns,
    sathiTurns,
    topicLines,
    recentTurns: recent,
    sessionCount: 1,
    availableRooms: [
      { roomId: conv.roomId, messageCount: conv.messageCount, updatedAt: conv.updatedAt },
    ],
    note: "Derived only from locally stored chat history turns. No LLM summary.",
  };
}

export function emptyConversationSummary(
  availableRooms: ConversationSummaryView["availableRooms"] = []
): ConversationSummaryView {
  return {
    empty: true,
    roomId: null,
    participants: [],
    humanTurns: 0,
    aiTurns: 0,
    dostTurns: 0,
    sathiTurns: 0,
    topicLines: [],
    recentTurns: [],
    sessionCount: 0,
    availableRooms,
    note: "No stored conversation yet. Join a Voice Room and complete turns to build a local summary.",
  };
}

/**
 * Build a summary for one room, or the most recently updated conversation.
 */
export function buildConversationSummary(
  store: ChatHistoryStore,
  roomId?: string | null
): ConversationSummaryView {
  const listed = listConversations(store).map((c) => ({
    roomId: c.roomId,
    messageCount: c.messageCount,
    updatedAt: c.updatedAt,
  }));

  if (listed.length === 0) {
    return emptyConversationSummary([]);
  }

  let conv: ChatHistoryConversation | null = null;
  if (roomId) {
    conv = getConversation(store, roomId);
  }
  if (!conv) {
    conv = listConversations(store)[0] || null;
  }
  if (!conv || conv.messages.length === 0) {
    return emptyConversationSummary(listed);
  }

  const view = summarizeConversation(conv);
  view.sessionCount = listed.length;
  view.availableRooms = listed;
  return view;
}

export function loadConversationSummary(
  roomId?: string | null,
  storage: Pick<Storage, "getItem"> | null = typeof window !== "undefined" ? localStorage : null
): ConversationSummaryView {
  return buildConversationSummary(loadChatHistoryStore(storage), roomId);
}
