"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  History,
  MessageSquare,
  Mic,
  Clock,
  Users,
  Bot,
  ChevronRight,
  Hash,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import {
  ChatHistoryConversation,
  ChatHistoryMessage,
  getConversation,
  listConversations,
  loadChatHistoryStore,
} from "@/lib/chatHistory";

function formatWhen(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

function MessageRow({ message }: { message: ChatHistoryMessage }) {
  const isAi = message.speakerType === "ai";
  return (
    <div className="p-4 flex gap-3 border-b border-slate-800/60 last:border-0">
      <div
        className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${
          isAi
            ? message.persona === "sathi"
              ? "bg-pink-950/50 text-pink-400"
              : "bg-purple-950/50 text-purple-400"
            : message.source === "text"
              ? "bg-blue-950/50 text-blue-400"
              : "bg-emerald-950/50 text-emerald-400"
        }`}
      >
        {isAi ? (
          <Bot className="w-4 h-4" />
        ) : message.source === "text" ? (
          <MessageSquare className="w-4 h-4" />
        ) : (
          <Mic className="w-4 h-4" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-xs text-slate-400 flex-wrap">
          <span className="font-semibold text-slate-200">{message.speakerName}</span>
          <span className="font-mono text-[10px] uppercase tracking-wider text-slate-500">
            {isAi
              ? message.persona
                ? `AI · ${message.persona}`
                : "AI"
              : "Human"}
          </span>
          <span className="flex items-center gap-1 ml-auto text-slate-500">
            <Clock className="w-3 h-3" />
            {formatWhen(message.timestamp)}
          </span>
        </div>
        <p className="text-sm text-slate-300 mt-1 leading-relaxed whitespace-pre-wrap">
          {message.text}
        </p>
      </div>
    </div>
  );
}

export default function ChatHistoryPage() {
  const [conversations, setConversations] = useState<ChatHistoryConversation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    try {
      setError(null);
      const store = loadChatHistoryStore();
      const list = listConversations(store);
      setConversations(list);
      setSelectedId((prev) => {
        if (prev && list.some((c) => c.id === prev)) return prev;
        return list[0]?.id ?? null;
      });
    } catch {
      setError("Unable to read local chat history.");
      setConversations([]);
      setSelectedId(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const selected = useMemo(() => {
    if (!selectedId) return null;
    return getConversation({ version: 2, conversations }, selectedId);
  }, [conversations, selectedId]);

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto p-6 md:p-8 space-y-6 h-full">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <History className="w-6 h-6 text-purple-400" />
            Chat History
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Completed room turns from this browser — voice, text, and AI replies.
          </p>
        </div>

        {loading ? (
          <div className="glass-card rounded-2xl border border-slate-800 p-12 flex flex-col items-center gap-3 text-slate-400">
            <Loader2 className="w-6 h-6 animate-spin text-purple-400" />
            <p className="text-sm">Loading history…</p>
          </div>
        ) : error ? (
          <div className="glass-card rounded-2xl border border-rose-900/50 p-8 flex items-start gap-3 text-rose-300">
            <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium">{error}</p>
              <button
                type="button"
                onClick={() => {
                  setLoading(true);
                  refresh();
                }}
                className="mt-3 text-xs text-slate-300 underline hover:text-white"
              >
                Retry
              </button>
            </div>
          </div>
        ) : conversations.length === 0 ? (
          <div className="glass-card rounded-2xl border border-slate-800 p-12 text-center space-y-2">
            <MessageSquare className="w-8 h-8 text-slate-600 mx-auto" />
            <p className="text-sm text-slate-400">No history yet</p>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              Join a voice room and complete a turn (speak or text). Final messages are saved
              locally here across refresh.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 min-h-[28rem]">
            <div className="lg:col-span-2 glass-card rounded-2xl border border-slate-800 overflow-hidden flex flex-col max-h-[70vh]">
              <div className="px-4 py-3 border-b border-slate-800 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Conversations ({conversations.length})
              </div>
              <div className="overflow-y-auto flex-1 divide-y divide-slate-800/80">
                {conversations.map((conv) => {
                  const active = conv.id === selectedId;
                  return (
                    <button
                      key={conv.id}
                      type="button"
                      onClick={() => setSelectedId(conv.id)}
                      className={`w-full text-left p-4 hover:bg-slate-900/50 transition-colors ${
                        active ? "bg-purple-950/30 border-l-2 border-purple-500" : "border-l-2 border-transparent"
                      }`}
                    >
                      <div className="flex items-start gap-2">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5 text-sm font-semibold text-white">
                            <Hash className="w-3.5 h-3.5 text-purple-400 flex-shrink-0" />
                            <span className="truncate font-mono text-xs md:text-sm">{conv.roomId}</span>
                          </div>
                          <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500">
                            <span className="flex items-center gap-1">
                              <Clock className="w-3 h-3" />
                              {formatWhen(conv.updatedAt)}
                            </span>
                            <span className="flex items-center gap-1">
                              <Users className="w-3 h-3" />
                              {conv.participantNames.length || "—"} human
                              {conv.participantNames.length === 1 ? "" : "s"}
                            </span>
                            <span className="flex items-center gap-1">
                              <MessageSquare className="w-3 h-3" />
                              {conv.messageCount} turn{conv.messageCount === 1 ? "" : "s"}
                            </span>
                          </div>
                          <p className="text-xs text-slate-400 mt-2 line-clamp-2">
                            {conv.latestPreview || "No preview"}
                          </p>
                        </div>
                        <ChevronRight
                          className={`w-4 h-4 flex-shrink-0 mt-1 ${
                            active ? "text-purple-400" : "text-slate-600"
                          }`}
                        />
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="lg:col-span-3 glass-card rounded-2xl border border-slate-800 overflow-hidden flex flex-col max-h-[70vh]">
              {selected ? (
                <>
                  <div className="px-4 py-3 border-b border-slate-800 space-y-1">
                    <h2 className="text-sm font-semibold text-white font-mono flex items-center gap-1.5">
                      <Hash className="w-3.5 h-3.5 text-purple-400" />
                      {selected.roomId}
                    </h2>
                    <p className="text-[11px] text-slate-500">
                      {selected.messageCount} turns · updated {formatWhen(selected.updatedAt)}
                      {selected.participantNames.length > 0
                        ? ` · ${selected.participantNames.join(", ")}`
                        : ""}
                    </p>
                  </div>
                  <div className="overflow-y-auto flex-1">
                    {selected.messages.length === 0 ? (
                      <div className="p-10 text-center text-sm text-slate-500">
                        No turns in this conversation.
                      </div>
                    ) : (
                      selected.messages.map((m) => <MessageRow key={m.id} message={m} />)
                    )}
                  </div>
                </>
              ) : (
                <div className="p-10 text-center text-sm text-slate-500">
                  Select a conversation to inspect its turns.
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
