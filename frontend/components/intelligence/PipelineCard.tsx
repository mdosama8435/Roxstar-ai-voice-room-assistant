"use client";

import React from "react";
import { Cpu, ArrowRight, Circle, CheckCircle2 } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { useLiveKit } from "@/hooks/LiveKitContext";
import {
  formatTtsPipelineLabel,
  isTtsPipelineActive,
} from "@/lib/ttsPipelineState";
import { cn } from "@/lib/utils";

export const PipelineCard: React.FC = () => {
  const {
    connectionState,
    sttState,
    llmStatus,
    ttsStatus,
    latestSTTLatencyMs,
    activeRouting,
  } = useLiveKit();
  const isConnected = connectionState === "CONNECTED";
  const isSTTActive = sttState === "ACTIVE";
  const llmBusy = llmStatus === "STREAMING" || llmStatus === "GENERATING";
  const llmFailed = llmStatus === "FAILED";
  const ttsBusy = isTtsPipelineActive(ttsStatus);
  const hasRoute =
    Boolean(activeRouting?.selectedBot) && activeRouting.selectedBot !== "NONE";
  const ttsLabel = formatTtsPipelineLabel(ttsStatus, isConnected);

  const stages = [
    {
      id: "livekit",
      name: "LiveKit",
      provider: "WebRTC SFU",
      ms: null as number | null,
      active: isConnected,
      status: isConnected ? "● ACTIVE" : "○ Not connected",
    },
    {
      id: "stt",
      name: "STT",
      provider: "Sarvam Saaras",
      ms: latestSTTLatencyMs ?? null,
      active: isSTTActive,
      status: isSTTActive
        ? "● ACTIVE"
        : sttState === "CONNECTING"
        ? "◌ CONNECTING"
        : isConnected
        ? "○ READY"
        : "○ Standby",
    },
    {
      id: "turn",
      name: "Turn",
      provider: "Detector",
      ms: null,
      active: false,
      status: isConnected ? "○ READY" : "○ Standby",
    },
    {
      id: "router",
      name: "Router",
      provider: "Arbitration",
      ms: null,
      active: isConnected && hasRoute,
      status: hasRoute ? "● ACTIVE" : isConnected ? "○ Waiting" : "○ Standby",
    },
    {
      id: "memory",
      name: "Memory",
      provider: "Room context",
      ms: null,
      active: false,
      status: isConnected ? "○ READY" : "○ Standby",
    },
    {
      id: "llm",
      name: "LLM",
      provider: "Configured LLM",
      ms: null,
      active: llmBusy,
      status: llmBusy
        ? "● STREAMING"
        : llmFailed
        ? "✕ FAILED"
        : llmStatus === "COMPLETED"
        ? "● COMPLETED"
        : llmStatus === "CANCELLED"
        ? "○ CANCELLED"
        : isConnected
        ? "○ STANDBY"
        : "○ Standby",
    },
    {
      id: "tts",
      name: "TTS",
      provider: "Sarvam Bulbul",
      ms: null,
      active: ttsBusy,
      status: ttsLabel,
    },
  ];

  const detailRows = [
    {
      label: "LiveKit Transport",
      ok: isConnected,
      status: isConnected ? "● ACTIVE" : "○ Not connected",
    },
    {
      label: "Sarvam Saaras STT",
      ok: isSTTActive,
      status: isSTTActive
        ? "● ACTIVE"
        : sttState === "CONNECTING"
        ? "◌ CONNECTING"
        : isConnected
        ? "○ READY"
        : "○ Standby",
    },
    {
      label: "Turn Detection",
      ok: false,
      status: isConnected ? "○ READY" : "○ Standby",
    },
    {
      label: "Dual-Bot Router",
      ok: hasRoute,
      status: hasRoute ? "● ACTIVE" : isConnected ? "○ Waiting" : "○ Standby",
    },
    {
      label: "Room Context / Memory",
      ok: false,
      status: isConnected ? "○ READY" : "○ Standby",
    },
    {
      label: "LLM Reasoning",
      ok: llmBusy,
      status: llmBusy
        ? "● STREAMING"
        : llmFailed
        ? "✕ FAILED"
        : llmStatus === "COMPLETED"
        ? "● COMPLETED"
        : isConnected
        ? "○ STANDBY"
        : "○ Standby",
    },
    {
      label: "Sarvam Bulbul TTS",
      ok: ttsBusy || ttsStatus === "completed",
      status: ttsLabel,
    },
  ];

  return (
    <div className="glass-card rounded-xl p-4 space-y-3 border border-slate-800">
      <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-300 uppercase tracking-wider">
          <Cpu className="w-4 h-4 text-purple-400" />
          <span>AI Pipeline (Live)</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className={cn(
              "px-2 py-0.5 rounded text-[10px] font-mono font-medium flex items-center gap-1",
              llmBusy
                ? "bg-purple-950/60 text-purple-300 border border-purple-800/60 animate-pulse"
                : llmFailed
                ? "bg-rose-950/60 text-rose-300 border border-rose-800/60"
                : "bg-slate-900 text-slate-300 border border-slate-800"
            )}
          >
            <span
              className={cn(
                "w-1.5 h-1.5 rounded-full",
                llmBusy ? "bg-purple-400 animate-pulse" : llmFailed ? "bg-rose-400" : "bg-slate-500"
              )}
            />
            LLM: {llmStatus}
          </span>
          <Badge variant={isConnected ? "emerald" : "outline"} size="sm" className="text-[10px]">
            {isConnected ? "LiveKit Active" : "Not connected"}
          </Badge>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-1 py-1 px-1">
        {stages.map((stage, idx) => (
          <React.Fragment key={stage.id}>
            <div className="flex flex-col items-center">
              <div
                className={`px-2 py-1 rounded-md border text-[11px] font-mono transition-colors ${
                  stage.active
                    ? "bg-emerald-950/50 border-emerald-800/60 text-emerald-300 shadow-sm"
                    : "bg-slate-900 border-slate-800 text-slate-400"
                }`}
              >
                {stage.name}
              </div>
              <span className="text-[9px] text-slate-500 mt-0.5 max-w-[64px] text-center truncate">
                {stage.ms != null ? `${stage.ms}ms` : stage.provider}
              </span>
            </div>
            {idx < stages.length - 1 && (
              <ArrowRight className="w-3 h-3 text-slate-600 flex-shrink-0" />
            )}
          </React.Fragment>
        ))}
      </div>

      {latestSTTLatencyMs != null && (
        <p className="text-[10px] text-slate-500 font-mono px-1">
          Last STT latency: {latestSTTLatencyMs}ms
        </p>
      )}

      <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/60 space-y-1.5 text-xs">
        <div className="flex items-center justify-between text-slate-300 font-medium pb-1 border-b border-slate-800/40">
          <span>Pipeline Component</span>
          <span>Status</span>
        </div>
        {detailRows.map((row) => (
          <div
            key={row.label}
            className={cn(
              "flex items-center justify-between",
              row.ok ? "text-slate-300" : "text-slate-500"
            )}
          >
            <span className="flex items-center gap-1.5">
              {row.ok ? (
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              ) : (
                <Circle className="w-3.5 h-3.5 text-slate-600" />
              )}
              {row.label}
            </span>
            <span
              className={cn(
                "font-mono",
                row.ok ? "text-emerald-400 font-medium" : "text-slate-500"
              )}
            >
              {row.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
