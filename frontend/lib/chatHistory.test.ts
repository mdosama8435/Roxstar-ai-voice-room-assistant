import { describe, expect, it } from "vitest";
import {
  classifyHistorySpeaker,
  getConversation,
  listConversations,
  loadChatHistoryStore,
  normalizeStore,
  persistCompletedTurn,
  shouldPersistTranscriptTurn,
  upsertHistoryMessage,
  type ChatHistoryStore,
} from "./chatHistory";

function memoryStorage(seed?: string): Storage {
  const map = new Map<string, string>();
  if (seed !== undefined) map.set("roxstar-chat-history", seed);
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

describe("chatHistory — persistence rules", () => {
  it("persists a completed final turn", () => {
    const storage = memoryStorage();
    const store = persistCompletedTurn(
      {
        id: "turn-1",
        roomId: "roxstar-demo",
        speakerId: "human-rahul",
        speakerName: "Rahul",
        text: "AI kya hota hai?",
        isFinal: true,
        source: "voice",
      },
      storage
    );
    expect(store.conversations).toHaveLength(1);
    expect(store.conversations[0].messageCount).toBe(1);
    expect(store.conversations[0].latestPreview).toContain("AI kya");
    expect(store.conversations[0].participantNames).toEqual(["Rahul"]);
  });

  it("does not persist partial STT as a final message", () => {
    const storage = memoryStorage();
    expect(
      shouldPersistTranscriptTurn({
        isFinal: false,
        text: "AI kya",
        id: "partial-1",
      })
    ).toBe(false);

    const store = persistCompletedTurn(
      {
        id: "partial-1",
        roomId: "roxstar-demo",
        speakerId: "human-rahul",
        speakerName: "Rahul",
        text: "AI kya",
        isFinal: false,
      },
      storage
    );
    expect(store.conversations).toHaveLength(0);
    expect(loadChatHistoryStore(storage).conversations).toHaveLength(0);
  });

  it("records human + AI turns with persona", () => {
    const storage = memoryStorage();
    persistCompletedTurn(
      {
        id: "turn-h",
        roomId: "room-a",
        speakerId: "human-priya",
        speakerName: "Priya",
        text: "AI Sathi, tum batao.",
        isFinal: true,
        source: "text",
      },
      storage
    );
    persistCompletedTurn(
      {
        id: "aievt-1",
        roomId: "room-a",
        speakerId: "ai_sathi",
        speakerName: "RoxStar AI Sathi",
        text: "Zaroor Priya!",
        isFinal: true,
        source: "ai",
      },
      storage
    );
    const conv = loadChatHistoryStore(storage).conversations[0];
    expect(conv.messageCount).toBe(2);
    expect(conv.messages[0].speakerType).toBe("human");
    expect(conv.messages[1].speakerType).toBe("ai");
    expect(conv.messages[1].persona).toBe("sathi");
    expect(classifyHistorySpeaker("ai_dost", "Roxstar AI Dost").persona).toBe("dost");
  });

  it("dedupes replayed / duplicate event ids", () => {
    let store: ChatHistoryStore = { version: 2, conversations: [] };
    const msg = {
      id: "turn-dup",
      roomId: "room-b",
      timestamp: new Date().toISOString(),
      speakerName: "Rahul",
      speakerType: "human" as const,
      text: "Hello",
      source: "voice" as const,
    };
    store = upsertHistoryMessage(store, msg);
    store = upsertHistoryMessage(store, msg);
    store = upsertHistoryMessage(store, { ...msg, text: "Hello again (replay)" });
    expect(store.conversations[0].messageCount).toBe(1);
    expect(store.conversations[0].messages[0].text).toBe("Hello");
  });

  it("survives reload via persistence layer", () => {
    const storage = memoryStorage();
    persistCompletedTurn(
      {
        id: "turn-reload",
        roomId: "room-c",
        speakerId: "human-rahul",
        speakerName: "Rahul",
        text: "Cricket pasand hai",
        isFinal: true,
      },
      storage
    );
    const reloaded = loadChatHistoryStore(storage);
    expect(reloaded.conversations[0].roomId).toBe("room-c");
    expect(reloaded.conversations[0].messages[0].text).toContain("Cricket");
  });

  it("empty history state", () => {
    const store = loadChatHistoryStore(memoryStorage());
    expect(listConversations(store)).toEqual([]);
    expect(getConversation(store, "missing")).toBeNull();
  });

  it("selecting a history item returns its turns", () => {
    const storage = memoryStorage();
    persistCompletedTurn(
      {
        id: "t1",
        roomId: "select-room",
        speakerId: "human-rahul",
        speakerName: "Rahul",
        text: "One",
        isFinal: true,
      },
      storage
    );
    persistCompletedTurn(
      {
        id: "t2",
        roomId: "select-room",
        speakerId: "ai_dost",
        speakerName: "RoxStar AI Dost",
        text: "Two",
        isFinal: true,
      },
      storage
    );
    const store = loadChatHistoryStore(storage);
    const selected = getConversation(store, "select-room");
    expect(selected).not.toBeNull();
    expect(selected!.messages.map((m) => m.text)).toEqual(["One", "Two"]);
  });

  it("skips empty text even when marked final", () => {
    expect(
      shouldPersistTranscriptTurn({ isFinal: true, text: "   ", id: "turn-empty" })
    ).toBe(false);
  });

  it("migrates legacy flat array format", () => {
    const legacy = JSON.stringify([
      {
        id: "voice-old",
        room: "legacy-room",
        speaker: "Rahul",
        text: "Old turn",
        kind: "voice",
        at: "2026-01-01T10:00:00.000Z",
      },
    ]);
    const store = normalizeStore(JSON.parse(legacy));
    expect(store.version).toBe(2);
    expect(store.conversations[0].roomId).toBe("legacy-room");
    expect(store.conversations[0].messages[0].text).toBe("Old turn");
  });
});
