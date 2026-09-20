"use client";

import React from "react";
import { Users, Clock, Wifi, WifiOff, Hash, AlertTriangle, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { useLiveKit } from "@/hooks/LiveKitContext";

export const Topbar: React.FC = () => {
  const {
    connectionState,
    roomName,
    participants,
    errorMessage,
    sttState,
    latestSTTLatencyMs,
  } = useLiveKit();

  const isConnected = connectionState === "CONNECTED";
  const isConnecting = connectionState === "CONNECTING";
  const isReconnecting = connectionState === "RECONNECTING";
  const isError = connectionState === "ERROR";
  const humanCount = participants.filter((p) => p.role !== "AI_AGENT").length;
  const aiCount = participants.filter((p) => p.role === "AI_AGENT").length;

  const renderConnectionBadge = () => {
    if (isConnected) {
      return (
        <div
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-950/40 border border-emerald-800/50 text-xs font-medium text-emerald-300"
          role="status"
          aria-label="LiveKit connected"
        >
          <Wifi className="w-3.5 h-3.5 text-emerald-400" aria-hidden />
          <span>LIVE</span>
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" aria-hidden />
        </div>
      );
    }
    if (isConnecting) {
      return (
        <div
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-950/40 border border-amber-800/50 text-xs font-medium text-amber-300"
          role="status"
          aria-label="Connecting to LiveKit"
        >
          <RefreshCw className="w-3.5 h-3.5 text-amber-400 animate-spin" aria-hidden />
          <span>CONNECTING</span>
        </div>
      );
    }
    if (isReconnecting) {
      return (
        <div
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-950/40 border border-amber-800/50 text-xs font-medium text-amber-300"
          role="status"
          aria-label="Reconnecting to LiveKit"
        >
          <RefreshCw className="w-3.5 h-3.5 text-amber-400 animate-spin" aria-hidden />
          <span>RECONNECTING</span>
        </div>
      );
    }
    if (isError) {
      return (
        <div
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-950/40 border border-rose-800/50 text-xs font-medium text-rose-300"
          role="status"
          aria-label="Connection error"
        >
          <AlertTriangle className="w-3.5 h-3.5 text-rose-400" aria-hidden />
          <span>ERROR</span>
        </div>
      );
    }
    return (
      <div
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-medium text-slate-400"
        role="status"
        aria-label="Disconnected"
      >
        <WifiOff className="w-3.5 h-3.5 text-slate-500" aria-hidden />
        <span>DISCONNECTED</span>
      </div>
    );
  };

  const participantLabel = !isConnected
    ? "Not connected"
    : `${humanCount} human${humanCount === 1 ? "" : "s"}${
        aiCount > 0 ? ` + ${aiCount} AI` : ""
      }`;

  const latencyLabel =
    typeof latestSTTLatencyMs === "number" && latestSTTLatencyMs > 0
      ? `${latestSTTLatencyMs}ms`
      : "Not available yet";

  return (
    <header className="min-h-16 md:h-20 w-full glass-panel border-b border-slate-800/80 px-3 sm:px-6 py-2 md:py-0 flex flex-col md:flex-row md:items-center md:justify-between gap-2 flex-shrink-0 z-10">
      <div className="min-w-0">
        <h1 className="text-base sm:text-xl font-bold tracking-tight text-white flex items-center gap-2 truncate">
          <span className="truncate">RoxStar AI Voice Room</span>
          <Badge variant="purple" size="sm" className="hidden sm:inline-flex flex-shrink-0">
            LiveKit
          </Badge>
        </h1>
        <p className="text-[11px] sm:text-xs text-slate-400 font-medium truncate">
          Real conversations. Real voices. More human.
        </p>
      </div>

      <div className="flex items-center gap-2 flex-wrap justify-end">
        <div className="flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg bg-slate-900/80 border border-slate-800 text-xs font-mono text-slate-300">
          <Hash className="w-3.5 h-3.5 text-purple-400 flex-shrink-0" aria-hidden />
          <span className="truncate max-w-[9rem] sm:max-w-[14rem]">
            {isConnected && roomName ? roomName : "no-room"}
          </span>
        </div>

        {renderConnectionBadge()}

        <div
          className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900/80 border border-slate-800 text-xs font-medium"
          aria-label={`STT ${sttState}`}
        >
          <span className="text-slate-400 font-mono text-[11px]">STT:</span>
          {sttState === "ACTIVE" ? (
            <span className="text-emerald-400 font-semibold flex items-center gap-1">
              ACTIVE
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" aria-hidden />
            </span>
          ) : sttState === "CONNECTING" || sttState === "RECONNECTING" ? (
            <span className="text-amber-400 font-semibold">{sttState}</span>
          ) : sttState === "ERROR" ? (
            <span className="text-rose-400 font-semibold">ERROR</span>
          ) : sttState === "DISABLED" ? (
            <span className="text-slate-500 font-mono">DISABLED</span>
          ) : (
            <span className="text-slate-500 font-mono">READY</span>
          )}
        </div>

        <div className="flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg bg-slate-900/80 border border-slate-800 text-xs font-medium text-slate-300">
          <Users className="w-3.5 h-3.5 text-blue-400" aria-hidden />
          <span className="whitespace-nowrap">{participantLabel}</span>
        </div>

        <div className="hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900/80 border border-slate-800 text-xs font-medium text-slate-400">
          <Clock className="w-3.5 h-3.5 text-slate-500" aria-hidden />
          <span>
            STT latency:{" "}
            <span className="text-slate-300 font-mono">{latencyLabel}</span>
          </span>
        </div>
      </div>

      {errorMessage ? (
        <div
          className="w-full order-last basis-full px-3 py-1.5 rounded-lg bg-rose-950/80 border border-rose-800/60 text-[11px] text-rose-200 truncate"
          role="alert"
        >
          {errorMessage}
        </div>
      ) : null}
    </header>
  );
};
