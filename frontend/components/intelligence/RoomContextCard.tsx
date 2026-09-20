"use client";

import React from "react";
import { Compass, User, Sparkles, MessageSquare, Globe } from "lucide-react";
import { useLiveKit } from "@/hooks/LiveKitContext";

export const RoomContextCard: React.FC = () => {
  const { roomContextState, activeRouting, participants, connectionState } = useLiveKit();
  const isConnected = connectionState === "CONNECTED";

  const speakerName = roomContextState?.activeSpeakerId
    ? participants.find((p) => p.id === roomContextState.activeSpeakerId)?.name || "Active Participant"
    : "None";

  return (
    <div className="glass-card rounded-xl p-4 space-y-3 border border-slate-800">
      <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-300 uppercase tracking-wider">
          <Compass className="w-4 h-4 text-purple-400" />
          <span>Room Context</span>
        </div>
        <span className="text-[10px] text-emerald-400 font-mono">
          {isConnected ? "● active (in-memory)" : "○ idle"}
        </span>
      </div>

      <div className="space-y-2.5 text-xs">
        <div className="flex items-center justify-between py-1 border-b border-slate-800/40">
          <span className="text-slate-400 flex items-center gap-1.5">
            <Compass className="w-3.5 h-3.5 text-purple-400" /> Current topic
          </span>
          <span className="text-slate-200 font-medium truncate max-w-[150px]">
            {roomContextState?.currentTopic || (isConnected ? "Waiting" : "Not connected")}
          </span>
        </div>

        <div className="flex items-center justify-between py-1 border-b border-slate-800/40">
          <span className="text-slate-400 flex items-center gap-1.5">
            <User className="w-3.5 h-3.5 text-cyan-400" /> Active speaker
          </span>
          <span className="text-slate-200 font-medium">
            {speakerName}
          </span>
        </div>

        <div className="flex items-center justify-between py-1 border-b border-slate-800/40">
          <span className="text-slate-400 flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-amber-400" /> Routed bot
          </span>
          <span className="text-slate-200 font-mono">
            {activeRouting?.selectedBot && activeRouting.selectedBot !== "NONE"
              ? activeRouting.selectedBot
              : "Standby"}
          </span>
        </div>

        <div className="flex items-center justify-between py-1 border-b border-slate-800/40">
          <span className="text-slate-400 flex items-center gap-1.5">
            <Globe className="w-3.5 h-3.5 text-emerald-400" /> Language style
          </span>
          <span className="text-slate-200 font-medium">
            {isConnected ? "Not available yet" : "Not connected"}
          </span>
        </div>

        <div className="flex items-center justify-between py-1">
          <span className="text-slate-400 flex items-center gap-1.5">
            <MessageSquare className="w-3.5 h-3.5 text-blue-400" /> Context turns
          </span>
          <span className="text-slate-200 font-mono">
            {roomContextState?.turnCount || 0} / 20 (FIFO)
          </span>
        </div>
      </div>
    </div>
  );
};

