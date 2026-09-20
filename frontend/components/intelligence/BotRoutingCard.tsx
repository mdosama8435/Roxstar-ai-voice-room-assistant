"use client";

import React from "react";
import { GitFork, ShieldCheck, Bot } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { useLiveKit } from "@/hooks/LiveKitContext";

/**
 * Shows real routing decision only — no invented confidence percentages.
 */
export const BotRoutingCard: React.FC = () => {
  const { activeRouting, connectionState } = useLiveKit();
  const isConnected = connectionState === "CONNECTED";

  const isDost = activeRouting?.selectedBot === "DOST";
  const isSathi = activeRouting?.selectedBot === "SATHI";
  const hasRoute = isDost || isSathi;
  const reason = (activeRouting?.reason || "").trim();

  return (
    <div className="glass-card rounded-xl p-4 space-y-3 border border-slate-800">
      <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-300 uppercase tracking-wider">
          <GitFork className="w-4 h-4 text-cyan-400" aria-hidden />
          <span>Bot Routing</span>
        </div>
        <Badge
          variant={activeRouting?.lockStatus === "ACQUIRED" ? "purple" : "outline"}
          size="sm"
          className="text-[10px]"
        >
          {activeRouting?.lockStatus === "ACQUIRED"
            ? "Lock acquired"
            : activeRouting?.lockStatus === "BLOCKED"
              ? "Lock deferred"
              : "Unlocked"}
        </Badge>
      </div>

      {!isConnected ? (
        <p className="text-xs text-slate-500 italic py-2">Not connected</p>
      ) : !hasRoute ? (
        <p className="text-xs text-slate-500 italic py-2">
          Waiting for speech or text turn — no bot selected yet
        </p>
      ) : (
        <div className="space-y-2">
          <div
            className={`flex items-center justify-between px-3 py-2.5 rounded-lg border ${
              isDost
                ? "bg-purple-950/40 border-purple-700/50 text-purple-200"
                : "bg-slate-950/40 border-slate-800 text-slate-500"
            }`}
          >
            <span className="flex items-center gap-1.5 text-xs font-medium">
              <Bot className="w-3.5 h-3.5" aria-hidden />
              AI Dost
            </span>
            <span className="text-[11px] font-mono">{isDost ? "Selected" : "—"}</span>
          </div>
          <div
            className={`flex items-center justify-between px-3 py-2.5 rounded-lg border ${
              isSathi
                ? "bg-pink-950/40 border-pink-700/50 text-pink-200"
                : "bg-slate-950/40 border-slate-800 text-slate-500"
            }`}
          >
            <span className="flex items-center gap-1.5 text-xs font-medium">
              <Bot className="w-3.5 h-3.5" aria-hidden />
              AI Sathi
            </span>
            <span className="text-[11px] font-mono">{isSathi ? "Selected" : "—"}</span>
          </div>
        </div>
      )}

      <div className="px-3 py-2 rounded-lg bg-slate-950/60 border border-slate-800/60 text-[11px] text-slate-400 space-y-1">
        <div className="flex items-center gap-1.5 text-slate-300 font-medium">
          <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" aria-hidden />
          <span>Reason</span>
        </div>
        <p className="text-slate-500 text-[10px] leading-snug">
          {reason || "Not available yet — awaiting an orchestration decision."}
        </p>
      </div>
    </div>
  );
};
