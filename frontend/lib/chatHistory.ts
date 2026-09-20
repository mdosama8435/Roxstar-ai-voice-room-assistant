/**
 * Browser-local chat history for RoxStar voice rooms.
 * Stores completed turns only (no partials, no audio, no secrets).
 */

export type SpeakerType = "human" | "ai";
export type HistorySource = "voice" | "text" | "ai";

export type HistorySelectedBot = "DOST" | "SATHI" | "NONE";

export interface ChatHistoryMessage {
  id: string;
  roomId: string;
  timestamp: string;
  speakerName: string;
  speakerType: SpeakerType;
  text: string;
  persona?: "dost" | "sathi";
  source: HistorySource;
  /** AI response latency when the source turn carried latency_ms. */
  latencyMs?: number;
  /** Present only when orchestration metadata was observed for this turn. */
  shouldRespond?: boolean;
  selectedBot?: HistorySelectedBot;
}

export interface ChatHistoryConversation {
  id: string;
  roomId: string;
  startedAt: string;
  updatedAt: string;
  participantNames: string[];
  messageCount: number;
  latestPreview: string;
  messages: ChatHistoryMessage[];
}

export const CHAT_HISTORY_STORAGE_KEY = "roxstar-chat-history";
export const MAX_CONVERSATIONS = 40;
export const MAX_MESSAGES_PER_CONVERSATION = 200;

/** Legacy flat entry shape from Phase 3F.2/3F.3 stub. */
interface LegacyFlatEntry {
  id: string;
  room: string;
  speaker: string;
  text: string;
  kind?: "voice" | "chat";
  at?: string;
}

export type ChatHistoryStore = {
  version: 2;
  conversations: ChatHistoryConversation[];
};

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof localStorage !== "undefined";
}

export function classifyHistorySpeaker(
  speakerId: string,
  speakerName?: string
): { speakerType: SpeakerType; persona?: "dost" | "sathi" } {
  const id = (speakerId || "").toLowerCase();
  const name = (speakerName || "").toLowerCase();
  if (id.includes("ai_dost") || id === "dost" || /\bdost\b/.test(name)) {
    return { speakerType: "ai", persona: "dost" };
  }
  if (id.includes("ai_sathi") || id === "sathi" || /\bsathi\b/.test(name) || /\bsaathi\b/.test(name)) {
    return { speakerType: "ai", persona: "sathi" };
  }
  if (id.startsWith("ai_") || name.includes("roxstar ai")) {
    return { speakerType: "ai" };
  }
  return { speakerType: "human" };
}

export function shouldPersistTranscriptTurn(input: {
  isFinal: boolean;
  text?: string | null;
  id?: string;
}): boolean {
  if (!input.isFinal) return false;
  const text = (input.text || "").trim();
  if (!text) return false;
  if (!input.id) return false;
  return true;
}

function recomputeConversation(conv: ChatHistoryConversation): ChatHistoryConversation {
  const messages = conv.messages.slice(-MAX_MESSAGES_PER_CONVERSATION);
  const names = Array.from(
    new Set(
      messages
        .filter((m) => m.speakerType === "human")
        .map((m) => m.speakerName)
        .filter(Boolean)
    )
  );
  const last = messages[messages.length - 1];
  return {
    ...conv,
    messages,
    messageCount: messages.length,
    participantNames: names,
    latestPreview: last ? last.text.slice(0, 140) : "",
    updatedAt: last?.timestamp || conv.updatedAt,
    startedAt: messages[0]?.timestamp || conv.startedAt,
  };
}

function legacyToStore(list: LegacyFlatEntry[]): ChatHistoryStore {
  const byRoom = new Map<string, ChatHistoryConversation>();
  for (const e of list) {
    const roomId = e.room || "unknown";
    const classified = classifyHistorySpeaker(e.speaker, e.speaker);
    const msg: ChatHistoryMessage = {
      id: e.id,
      roomId,
      timestamp: e.at ? new Date(e.at).toISOString() : new Date().toISOString(),
      speakerName: e.speaker,
      speakerType: classified.speakerType,
      text: e.text,
      persona: classified.persona,
      source: e.kind === "chat" ? "text" : classified.speakerType === "ai" ? "ai" : "voice",
    };
    // Fix invalid date
    if (Number.isNaN(Date.parse(msg.timestamp))) {
      msg.timestamp = new Date().toISOString();
    }
    let conv = byRoom.get(roomId);
    if (!conv) {
      conv = {
        id: roomId,
        roomId,
        startedAt: msg.timestamp,
        updatedAt: msg.timestamp,
        participantNames: [],
        messageCount: 0,
        latestPreview: "",
        messages: [],
      };
      byRoom.set(roomId, conv);
    }
    if (!conv.messages.some((m) => m.id === msg.id)) {
      conv.messages.push(msg);
    }
  }
  const conversations = Array.from(byRoom.values())
    .map(recomputeConversation)
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
    .slice(0, MAX_CONVERSATIONS);
  return { version: 2, conversations };
}

export function normalizeStore(raw: unknown): ChatHistoryStore {
  if (!raw) return { version: 2, conversations: [] };
  if (Array.isArray(raw)) {
    return legacyToStore(raw as LegacyFlatEntry[]);
  }
  if (typeof raw === "object" && raw !== null && "conversations" in raw) {
    const obj = raw as ChatHistoryStore;
    const conversations = (obj.conversations || [])
      .map((c) =>
        recomputeConversation({
          ...c,
          messages: Array.isArray(c.messages) ? c.messages : [],
        })
      )
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      .slice(0, MAX_CONVERSATIONS);
    return { version: 2, conversations };
  }
  return { version: 2, conversations: [] };
}

export function loadChatHistoryStore(
  storage: Pick<Storage, "getItem"> | null = isBrowser() ? localStorage : null
): ChatHistoryStore {
  if (!storage) return { version: 2, conversations: [] };
  try {
    const raw = storage.getItem(CHAT_HISTORY_STORAGE_KEY);
    if (!raw) return { version: 2, conversations: [] };
    return normalizeStore(JSON.parse(raw));
  } catch {
    return { version: 2, conversations: [] };
  }
}

export function saveChatHistoryStore(
  store: ChatHistoryStore,
  storage: Pick<Storage, "setItem"> | null = isBrowser() ? localStorage : null
): void {
  if (!storage) return;
  const bounded: ChatHistoryStore = {
    version: 2,
    conversations: store.conversations
      .map(recomputeConversation)
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      .slice(0, MAX_CONVERSATIONS),
  };
  storage.setItem(CHAT_HISTORY_STORAGE_KEY, JSON.stringify(bounded));
}

/**
 * Upsert a completed message into the room conversation.
 * Deduplicates by message id (and request/turn id callers pass as id).
 */
export function upsertHistoryMessage(
  store: ChatHistoryStore,
  message: ChatHistoryMessage
): ChatHistoryStore {
  const text = (message.text || "").trim();
  if (!text || !message.id || !message.roomId || message.roomId === "unknown") {
    return store;
  }

  const conversations = [...store.conversations];
  let idx = conversations.findIndex((c) => c.roomId === message.roomId);
  if (idx < 0) {
    conversations.unshift({
      id: message.roomId,
      roomId: message.roomId,
      startedAt: message.timestamp,
      updatedAt: message.timestamp,
      participantNames: [],
      messageCount: 0,
      latestPreview: "",
      messages: [],
    });
    idx = 0;
  }

  const conv = { ...conversations[idx], messages: [...conversations[idx].messages] };
  if (conv.messages.some((m) => m.id === message.id)) {
    return store;
  }
  conv.messages.push({ ...message, text });
  conversations[idx] = recomputeConversation(conv);

  return {
    version: 2,
    conversations: conversations
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      .slice(0, MAX_CONVERSATIONS),
  };
}

export function persistCompletedTurn(
  input: {
    id: string;
    roomId: string;
    speakerId: string;
    speakerName: string;
    text: string;
    isFinal: boolean;
    source?: HistorySource;
    timestamp?: string;
    latencyMs?: number;
    shouldRespond?: boolean;
    selectedBot?: HistorySelectedBot;
  },
  storage: Pick<Storage, "getItem" | "setItem"> | null = isBrowser() ? localStorage : null
): ChatHistoryStore {
  if (!shouldPersistTranscriptTurn(input)) {
    return loadChatHistoryStore(storage);
  }
  const classified = classifyHistorySpeaker(input.speakerId, input.speakerName);
  const source: HistorySource =
    input.source ||
    (classified.speakerType === "ai"
      ? "ai"
      : input.id.startsWith("turn-txt") || input.id.startsWith("chat-")
        ? "text"
        : "voice");

  const message: ChatHistoryMessage = {
    id: input.id,
    roomId: input.roomId,
    timestamp: input.timestamp || new Date().toISOString(),
    speakerName: input.speakerName || input.speakerId || "Speaker",
    speakerType: classified.speakerType,
    text: input.text.trim(),
    persona: classified.persona,
    source,
  };
  if (typeof input.latencyMs === "number" && Number.isFinite(input.latencyMs) && input.latencyMs >= 0) {
    message.latencyMs = input.latencyMs;
  }
  if (typeof input.shouldRespond === "boolean") {
    message.shouldRespond = input.shouldRespond;
  }
  if (input.selectedBot === "DOST" || input.selectedBot === "SATHI" || input.selectedBot === "NONE") {
    message.selectedBot = input.selectedBot;
  }

  const next = upsertHistoryMessage(loadChatHistoryStore(storage), message);
  saveChatHistoryStore(next, storage);
  return next;
}

/**
 * Merge orchestration / latency onto an already-persisted turn
 * (orchestration often arrives after the final STT commit).
 */
export function enrichHistoryMessage(
  input: {
    id: string;
    roomId: string;
    latencyMs?: number;
    shouldRespond?: boolean;
    selectedBot?: HistorySelectedBot;
  },
  storage: Pick<Storage, "getItem" | "setItem"> | null = isBrowser() ? localStorage : null
): ChatHistoryStore {
  const store = loadChatHistoryStore(storage);
  if (!input.id || !input.roomId || input.roomId === "unknown") return store;

  const conversations = [...store.conversations];
  const idx = conversations.findIndex((c) => c.roomId === input.roomId);
  if (idx < 0) return store;

  const conv = { ...conversations[idx], messages: [...conversations[idx].messages] };
  const msgIdx = conv.messages.findIndex((m) => m.id === input.id);
  if (msgIdx < 0) return store;

  const prev = conv.messages[msgIdx];
  const nextMsg: ChatHistoryMessage = { ...prev };
  let changed = false;

  if (
    typeof input.latencyMs === "number" &&
    Number.isFinite(input.latencyMs) &&
    input.latencyMs >= 0 &&
    nextMsg.latencyMs !== input.latencyMs
  ) {
    nextMsg.latencyMs = input.latencyMs;
    changed = true;
  }
  if (typeof input.shouldRespond === "boolean" && nextMsg.shouldRespond !== input.shouldRespond) {
    nextMsg.shouldRespond = input.shouldRespond;
    changed = true;
  }
  if (
    (input.selectedBot === "DOST" || input.selectedBot === "SATHI" || input.selectedBot === "NONE") &&
    nextMsg.selectedBot !== input.selectedBot
  ) {
    nextMsg.selectedBot = input.selectedBot;
    changed = true;
  }

  if (!changed) return store;

  conv.messages[msgIdx] = nextMsg;
  conversations[idx] = recomputeConversation(conv);
  const next: ChatHistoryStore = {
    version: 2,
    conversations: conversations.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)),
  };
  saveChatHistoryStore(next, storage);
  return next;
}

export function listConversations(store: ChatHistoryStore): ChatHistoryConversation[] {
  return [...store.conversations].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export function getConversation(
  store: ChatHistoryStore,
  conversationId: string
): ChatHistoryConversation | null {
  return store.conversations.find((c) => c.id === conversationId || c.roomId === conversationId) || null;
}
