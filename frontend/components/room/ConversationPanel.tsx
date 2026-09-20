"use client";

import React, { useState } from "react";
import { MessageSquare, Radio, Activity, BarChart2, Info, CheckCircle2, AlertTriangle, Mic, Zap, Globe, Bot, Sparkles } from "lucide-react";
import { TextChat } from "./TextChat";
import { TabType } from "@/types";
import { cn } from "@/lib/utils";
import { useLiveKit } from "@/hooks/LiveKitContext";
import { Badge } from "@/components/ui/Badge";

export const ConversationPanel: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>("conversation");
  const {
    eventLog,
    connectionState,
    participants,
    roomName,
    isMicEnabled,
    sttState,
    transcripts,
    latestSTTLatencyMs,
    activeStreamingPreview,
    llmStatus,
  } = useLiveKit();

  return (
    <div className="glass-card rounded-2xl flex flex-col flex-1 min-h-[360px] overflow-hidden border border-slate-800">
      {/* Tabs Header */}
      <div className="flex items-center justify-between border-b border-slate-800 px-2 sm:px-4 pt-3 flex-shrink-0 bg-slate-950/40 gap-2">
        <div
          className="flex items-center gap-1 sm:gap-2 overflow-x-auto scrollbar-thin pb-0 min-w-0"
          role="tablist"
          aria-label="Conversation panels"
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "conversation"}
            onClick={() => setActiveTab("conversation")}
            className={cn(
              "flex items-center gap-2 px-3 py-2 text-xs font-semibold rounded-t-lg border-b-2 transition-all whitespace-nowrap focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500/50",
              activeTab === "conversation"
                ? "border-purple-500 text-purple-300 bg-purple-500/10"
                : "border-transparent text-slate-400 hover:text-slate-200"
            )}
          >
            <Radio className="w-3.5 h-3.5" />
            <span>Conversation</span>
            {sttState === "ACTIVE" && (
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            )}
            {transcripts.length > 0 && (
              <Badge variant="purple" size="sm" className="text-[9px] px-1.5 py-0">
                {transcripts.length}
              </Badge>
            )}
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "chat"}
            onClick={() => setActiveTab("chat")}
            className={cn(
              "flex items-center gap-2 px-3 py-2 text-xs font-semibold rounded-t-lg border-b-2 transition-all whitespace-nowrap focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500/50",
              activeTab === "chat"
                ? "border-purple-500 text-purple-300 bg-purple-500/10"
                : "border-transparent text-slate-400 hover:text-slate-200"
            )}
          >
            <MessageSquare className="w-3.5 h-3.5" />
            <span>Text Chat</span>
            {connectionState === "CONNECTED" && (
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            )}
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "events"}
            onClick={() => setActiveTab("events")}
            className={cn(
              "flex items-center gap-2 px-3 py-2 text-xs font-semibold rounded-t-lg border-b-2 transition-all whitespace-nowrap focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500/50",
              activeTab === "events"
                ? "border-purple-500 text-purple-300 bg-purple-500/10"
                : "border-transparent text-slate-400 hover:text-slate-200"
            )}
          >
            <Activity className="w-3.5 h-3.5" />
            <span>Events</span>
            {eventLog.length > 0 && (
              <Badge variant="purple" size="sm" className="text-[9px] px-1.5 py-0">
                {eventLog.length}
              </Badge>
            )}
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "analytics"}
            onClick={() => setActiveTab("analytics")}
            className={cn(
              "flex items-center gap-2 px-3 py-2 text-xs font-semibold rounded-t-lg border-b-2 transition-all whitespace-nowrap focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500/50",
              activeTab === "analytics"
                ? "border-purple-500 text-purple-300 bg-purple-500/10"
                : "border-transparent text-slate-400 hover:text-slate-200"
            )}
          >
            <BarChart2 className="w-3.5 h-3.5" />
            <span>Room Stats</span>
          </button>
        </div>

        <div className="pb-2 text-[11px] text-slate-500 flex items-center gap-1">
          <Info className="w-3 h-3" />
          <span>LiveKit WebRTC Channel</span>
        </div>
      </div>

      {/* Tab Content Area */}
      <div className="flex-1 p-5 overflow-y-auto">
        {/* VOICE TRANSCRIPTS TAB */}
        {activeTab === "conversation" && (
          <div className="h-full flex flex-col space-y-3">
            {/* STT Status & Metrics Banner */}
            <div className="flex items-center justify-between pb-2 border-b border-slate-800/80 text-xs">
              <div className="flex items-center gap-2">
                <span className="text-slate-400 font-medium">Pipeline:</span>
                <span
                  className={cn(
                    "px-2 py-0.5 rounded text-[11px] font-mono font-medium flex items-center gap-1",
                    sttState === "ACTIVE"
                      ? "bg-emerald-950/60 text-emerald-300 border border-emerald-800/60"
                      : sttState === "CONNECTING" || sttState === "RECONNECTING"
                      ? "bg-amber-950/60 text-amber-300 border border-amber-800/60"
                      : sttState === "DISABLED"
                      ? "bg-slate-900 text-slate-400 border border-slate-800"
                      : sttState === "ERROR"
                      ? "bg-rose-950/60 text-rose-300 border border-rose-800/60"
                      : "bg-slate-900 text-slate-500 border border-slate-800"
                  )}
                >
                  <span
                    className={cn(
                      "w-1.5 h-1.5 rounded-full",
                      sttState === "ACTIVE"
                        ? "bg-emerald-400 animate-pulse"
                        : sttState === "CONNECTING"
                        ? "bg-amber-400 animate-spin"
                        : sttState === "ERROR"
                        ? "bg-rose-400"
                        : "bg-slate-500"
                    )}
                  />
                  STT: {sttState}
                </span>

                {latestSTTLatencyMs && (
                  <span className="flex items-center gap-1 text-[11px] text-purple-300 font-mono bg-purple-950/50 px-2 py-0.5 rounded border border-purple-800/40">
                    <Zap className="w-3 h-3 text-purple-400" />
                    {latestSTTLatencyMs} ms
                  </span>
                )}
              </div>

              <span className="text-[10px] text-slate-500 font-mono">
                saaras:v3-realtime (auto)
              </span>
            </div>

            {/* Transcript List or Empty State */}
            {transcripts.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center p-8 space-y-3">
                <div className="w-12 h-12 rounded-2xl bg-purple-950/40 border border-purple-800/30 flex items-center justify-center text-purple-400 shadow-glow-purple">
                  <Mic className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-sm font-medium text-slate-200">
                    {isMicEnabled
                      ? "Ready for speech — Speak in Hindi, Hinglish, or English"
                      : "Unmute microphone to begin real-time speech recognition"}
                  </h3>
                  <p className="text-xs text-slate-500 max-w-md mt-1.5 leading-relaxed">
                    Speech streams through AudioWorklet 16kHz PCM resampling directly into Sarvam Saaras.
                    Interim partials and finalized turns with speaker attribution will render here.
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-3 overflow-y-auto max-h-[340px] pr-1">
                {transcripts.map((turn) => (
                  <div
                    key={turn.id}
                    className={cn(
                      "p-3 rounded-xl border transition-all text-xs space-y-1.5",
                      turn.isFinal
                        ? "bg-slate-900/70 border-slate-800/80"
                        : "bg-purple-950/20 border-purple-800/50 shadow-sm animate-pulse"
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-200 flex items-center gap-1.5">
                          {turn.speakerId.startsWith("ai_") ? (
                            turn.speakerId === "ai_dost" ? (
                              <Bot className="w-3.5 h-3.5 text-blue-400" />
                            ) : (
                              <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                            )
                          ) : null}
                          {turn.speakerName}
                          {turn.isLocal && (
                            <span className="text-[10px] font-normal text-slate-400">(You)</span>
                          )}
                        </span>
                        {turn.speakerId.startsWith("ai_") ? (
                          <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-purple-950/60 border border-purple-800/40 text-purple-300 font-mono flex items-center gap-1">
                            <Sparkles className="w-2.5 h-2.5 text-purple-400" />
                            AI Response (Gemini)
                          </span>
                        ) : (
                          <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-blue-950/60 border border-blue-800/40 text-blue-300 font-mono">
                            Human Transcript
                          </span>
                        )}
                        {turn.detectedLanguage && (
                          <span className="text-[9px] flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                            <Globe className="w-2.5 h-2.5 text-slate-400" />
                            {turn.detectedLanguage}
                          </span>
                        )}
                        {!turn.isFinal && (
                          <span className="text-[9px] text-purple-400 font-mono italic">
                            ● interim...
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        {turn.latencyMs && (
                          <span className="text-[10px] text-emerald-400 font-mono flex items-center gap-0.5">
                            <Zap className="w-2.5 h-2.5" />
                            {turn.latencyMs} ms
                          </span>
                        )}
                        <span className="text-[10px] text-slate-500 font-mono">
                          {turn.timestamp}
                        </span>
                      </div>
                    </div>

                    <p className="text-slate-100 text-sm leading-relaxed pl-1 border-l-2 border-purple-500/40">
                      {turn.text}
                    </p>

                    {/* Phase 3B Orchestration State Badges */}
                    {turn.orchestration ? (
                      <div className="pt-1.5 flex flex-wrap items-center gap-1.5 border-t border-slate-800/60 text-[10px] font-mono">
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-950/40 text-emerald-300 border border-emerald-800/40">
                          <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                          Turn completed
                        </span>
                        {turn.orchestration.shouldRespond ? (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-purple-950/40 text-purple-300 border border-purple-800/40">
                            <CheckCircle2 className="w-3 h-3 text-purple-400" />
                            Response required
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-900 text-slate-400 border border-slate-800">
                            ○ No response required
                          </span>
                        )}
                        {turn.orchestration.selectedBot !== "NONE" && (
                          <span
                            className={cn(
                              "inline-flex items-center gap-1 px-1.5 py-0.5 rounded border",
                              turn.orchestration.selectedBot === "DOST"
                                ? "bg-blue-950/40 text-blue-300 border-blue-800/40"
                                : "bg-purple-950/40 text-purple-300 border-purple-800/40"
                            )}
                          >
                            → Routed to {turn.orchestration.selectedBot === "DOST" ? "AI Dost" : "AI Sathi"}
                          </span>
                        )}
                        {turn.orchestration.turnLockAcquired && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-cyan-950/40 text-cyan-300 border border-cyan-800/40">
                            🔒 Response lock acquired
                          </span>
                        )}
                        {turn.orchestration.lockDeferred && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-950/40 text-amber-300 border border-amber-800/40">
                            ⏳ Response deferred — room response locked
                          </span>
                        )}
                      </div>
                    ) : turn.isFinal && !turn.speakerId.startsWith("ai_") ? (
                      <div className="pt-1 flex items-center gap-1 text-[10px] text-slate-500 font-mono">
                        <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                        <span>Turn completed</span>
                      </div>
                    ) : null}
                  </div>
                ))}

                {/* Ephemeral Streaming Preview Card */}
                {activeStreamingPreview && (
                  <div className="p-3 rounded-xl border bg-purple-950/20 border-purple-800/50 shadow-sm animate-pulse space-y-1.5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-purple-200 flex items-center gap-1.5">
                          <Bot className="w-3.5 h-3.5 text-purple-400 animate-spin" />
                          {activeStreamingPreview.botDisplayName}
                        </span>
                        <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-purple-950/60 border border-purple-800/40 text-purple-300 font-mono">
                          AI Generating...
                        </span>
                      </div>
                      <span className="text-[10px] text-purple-400 font-mono italic">
                        ● streaming tokens...
                      </span>
                    </div>
                    <p className="text-purple-100 text-sm leading-relaxed pl-1 border-l-2 border-purple-500/60 italic">
                      {activeStreamingPreview.text || "Thinking..."}
                      <span className="inline-block w-1.5 h-3.5 ml-1 bg-purple-400 animate-pulse" />
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* TEXT CHAT TAB */}
        {activeTab === "chat" && <TextChat />}

        {/* EVENTS TAB (REAL LIVEKIT EVENTS) */}
        {activeTab === "events" && (
          <div className="h-full flex flex-col space-y-2">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800 text-xs text-slate-400">
              <span className="font-medium">LiveKit Lifecycle Event Log</span>
              <span className="text-[10px] text-slate-500 font-mono">
                {eventLog.length} events captured
              </span>
            </div>

            {eventLog.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center p-8 space-y-2">
                <Activity className="w-6 h-6 text-slate-600" />
                <p className="text-xs text-slate-400">No room events recorded yet</p>
                <p className="text-[11px] text-slate-500">
                  Connect to the room to see participant joins, leaves, and track updates.
                </p>
              </div>
            ) : (
              <div className="space-y-1.5 overflow-y-auto max-h-[320px] pr-1">
                {eventLog.map((evt) => (
                  <div
                    key={evt.id}
                    className="p-2 rounded-lg bg-slate-900/60 border border-slate-800/60 flex items-center justify-between text-xs"
                  >
                    <div className="flex items-center gap-2">
                      {evt.level === "success" ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                      ) : evt.level === "warning" ? (
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
                      ) : evt.level === "error" ? (
                        <AlertTriangle className="w-3.5 h-3.5 text-rose-400 flex-shrink-0" />
                      ) : (
                        <Activity className="w-3.5 h-3.5 text-purple-400 flex-shrink-0" />
                      )}
                      <span className="text-slate-200">{evt.message}</span>
                    </div>

                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className="text-[10px] font-mono text-slate-500 px-1.5 py-0.5 rounded bg-slate-800/50">
                        {evt.type}
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        {evt.timestamp}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}


        {/* ROOM STATS TAB */}
        {activeTab === "analytics" && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800">
                <p className="text-[11px] text-slate-500 uppercase tracking-wider">Room</p>
                <p className="text-sm font-semibold text-slate-200 font-mono mt-0.5">{roomName}</p>
              </div>
              <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800">
                <p className="text-[11px] text-slate-500 uppercase tracking-wider">Connection</p>
                <p className="text-sm font-semibold text-emerald-400 mt-0.5">{connectionState}</p>
              </div>
              <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800">
                <p className="text-[11px] text-slate-500 uppercase tracking-wider">Participants</p>
                <p className="text-sm font-semibold text-blue-400 mt-0.5">{participants.length}</p>
              </div>
              <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800">
                <p className="text-[11px] text-slate-500 uppercase tracking-wider">Local Mic</p>
                <p className="text-sm font-semibold text-purple-400 mt-0.5">{isMicEnabled ? "Enabled" : "Muted"}</p>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800/80 text-xs text-slate-400 space-y-2">
              <p className="text-slate-300 font-medium">Real-time WebRTC Telemetry</p>
              <p className="text-slate-500 text-[11px] leading-relaxed">
                Audio and data messages are streamed directly through the LiveKit Selective Forwarding Unit (SFU).
                Artificial latencies, simulated transcripts, and fake AI performance numbers are strictly prohibited.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
