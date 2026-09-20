"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Sparkles,
  Copy,
  Check,
  Users,
  MessageSquare,
  Bot,
  Clock,
  Hash,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import {
  type ConversationSummaryView,
  loadConversationSummary,
} from "@/lib/conversationSummary";
import { CHAT_HISTORY_STORAGE_KEY } from "@/lib/chatHistory";

function formatWhen(iso?: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

export default function ConversationSummaryPage() {
  const [copied, setCopied] = useState(false);
  const [roomId, setRoomId] = useState<string | null>(null);
  const [view, setView] = useState<ConversationSummaryView | null>(null);

  const refresh = useCallback(() => {
    setView(loadConversationSummary(roomId));
  }, [roomId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === CHAT_HISTORY_STORAGE_KEY || e.key === null) refresh();
    };
    window.addEventListener("storage", onStorage);
    window.addEventListener("focus", refresh);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("focus", refresh);
    };
  }, [refresh]);

  const handleCopy = async () => {
    if (!view || view.empty) return;
    const lines = [
      `Room: ${view.roomId}`,
      `Participants: ${view.participants.join(", ") || "—"}`,
      `Human turns: ${view.humanTurns}`,
      `AI turns: ${view.aiTurns} (Dost ${view.dostTurns}, Sathi ${view.sathiTurns})`,
      "",
      "Topic lines (from human turns):",
      ...view.topicLines.map((t) => `- ${t}`),
      "",
      "Recent turns:",
      ...view.recentTurns.map((t) => `${t.speakerName}: ${t.text}`),
    ];
    await navigator.clipboard.writeText(lines.join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto p-8 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Sparkles className="w-6 h-6 text-amber-400" />
              Conversation Summary
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              Deterministic local overview from stored chat history — no LLM rewrite.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {view && view.availableRooms.length > 0 ? (
              <select
                className="bg-slate-900/80 border border-slate-700 rounded-lg text-xs text-slate-200 px-3 py-2"
                value={roomId ?? view.roomId ?? ""}
                onChange={(e) => setRoomId(e.target.value || null)}
                aria-label="Select room"
              >
                {view.availableRooms.map((r) => (
                  <option key={r.roomId} value={r.roomId}>
                    {r.roomId} ({r.messageCount})
                  </option>
                ))}
              </select>
            ) : null}
            <button
              type="button"
              onClick={handleCopy}
              disabled={!view || view.empty}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300 hover:text-white disabled:opacity-40"
            >
              {copied ? (
                <Check className="w-3.5 h-3.5 text-emerald-400" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        </div>

        {!view ? (
          <div className="glass-card rounded-2xl border border-slate-800 p-8 text-center text-sm text-slate-500">
            Loading…
          </div>
        ) : view.empty ? (
          <div className="glass-card rounded-2xl border border-dashed border-slate-800 p-10 text-center space-y-3">
            <Sparkles className="w-10 h-10 text-slate-600 mx-auto" />
            <h2 className="text-lg font-semibold text-slate-200">No conversation yet</h2>
            <p className="text-sm text-slate-400 max-w-md mx-auto">{view.note}</p>
            <Link
              href="/room/demo"
              className="inline-flex text-xs font-semibold text-purple-300 hover:text-purple-200"
            >
              Open Voice Room →
            </Link>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="glass-card rounded-2xl border border-slate-800 p-4 space-y-1">
                <p className="text-[10px] uppercase tracking-wider text-slate-500 flex items-center gap-1">
                  <Hash className="w-3 h-3" /> Room
                </p>
                <p className="text-sm font-mono text-purple-300 truncate">{view.roomId}</p>
              </div>
              <div className="glass-card rounded-2xl border border-slate-800 p-4 space-y-1">
                <p className="text-[10px] uppercase tracking-wider text-slate-500 flex items-center gap-1">
                  <Users className="w-3 h-3" /> Participants
                </p>
                <p className="text-sm text-white">
                  {view.participants.length
                    ? view.participants.join(", ")
                    : "—"}
                </p>
              </div>
              <div className="glass-card rounded-2xl border border-slate-800 p-4 space-y-1">
                <p className="text-[10px] uppercase tracking-wider text-slate-500 flex items-center gap-1">
                  <MessageSquare className="w-3 h-3" /> Human / AI
                </p>
                <p className="text-sm text-white tabular-nums">
                  {view.humanTurns} / {view.aiTurns}
                </p>
              </div>
              <div className="glass-card rounded-2xl border border-slate-800 p-4 space-y-1">
                <p className="text-[10px] uppercase tracking-wider text-slate-500 flex items-center gap-1">
                  <Bot className="w-3 h-3" /> Dost / Sathi
                </p>
                <p className="text-sm text-white tabular-nums">
                  {view.dostTurns} / {view.sathiTurns}
                </p>
              </div>
            </div>

            <div className="glass-card rounded-2xl border border-slate-800 p-5 space-y-2">
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <Clock className="w-3.5 h-3.5" />
                {formatWhen(view.startedAt)} → {formatWhen(view.updatedAt)}
                {view.durationLabel ? ` · ${view.durationLabel}` : ""}
                {view.sessionCount > 1
                  ? ` · ${view.sessionCount} sessions in this browser`
                  : ""}
              </div>
              <p className="text-[11px] text-slate-500">{view.note}</p>
            </div>

            <div className="glass-card rounded-2xl border border-slate-800 p-5 space-y-3">
              <h2 className="text-sm font-semibold text-slate-200">
                Main turns (from history)
              </h2>
              {view.topicLines.length === 0 ? (
                <p className="text-xs text-slate-500">No human turns to list.</p>
              ) : (
                <ul className="space-y-2">
                  {view.topicLines.map((line, i) => (
                    <li key={`${i}-${line.slice(0, 24)}`} className="text-xs text-slate-300">
                      <span className="text-slate-500 mr-2">{i + 1}.</span>
                      {line}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="glass-card rounded-2xl border border-slate-800 p-5 space-y-3">
              <h2 className="text-sm font-semibold text-slate-200">Recent conversation turns</h2>
              <ul className="divide-y divide-slate-800/80">
                {view.recentTurns.map((t, i) => (
                  <li key={`${t.timestamp}-${i}`} className="py-3 space-y-1">
                    <div className="flex items-center gap-2 text-[11px] text-slate-500">
                      <span className="font-semibold text-slate-200">{t.speakerName}</span>
                      <span className="uppercase tracking-wider">
                        {t.speakerType === "ai"
                          ? t.persona
                            ? `AI · ${t.persona}`
                            : "AI"
                          : "Human"}
                      </span>
                      <span className="ml-auto">{formatWhen(t.timestamp)}</span>
                    </div>
                    <p className="text-sm text-slate-300 whitespace-pre-wrap">{t.text}</p>
                  </li>
                ))}
              </ul>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}
