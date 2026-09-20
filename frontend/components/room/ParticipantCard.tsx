"use client";

import React from "react";
import { Mic, MicOff, Volume2, Sparkles, User } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { ParticipantUI } from "@/types";
import { cn } from "@/lib/utils";

interface ParticipantCardProps {
  participant: ParticipantUI;
}

export const ParticipantCard: React.FC<ParticipantCardProps> = ({ participant }) => {
  const isAI = participant.role === "AI_AGENT";
  const isGenerating = Boolean(
    participant.badgeText?.includes("GENERATING") ||
      participant.badgeText?.includes("Responding")
  );

  // State badge color & label mappings
  const renderStateBadge = () => {
    if (isAI) {
      if (isGenerating) {
        return (
          <Badge variant="amber" size="sm" className="animate-pulse flex items-center gap-1 text-amber-300 border-amber-500/40">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping" />
            LLM GENERATING
          </Badge>
        );
      }
      return (
        <Badge variant="emerald" size="sm" className="text-[10px]">
          Ready
        </Badge>
      );
    }

    if (participant.mediaState === "SPEAKING" || participant.isSpeaking) {
      return (
        <Badge variant="emerald" size="sm" className="animate-pulse">
          <Volume2 className="w-3 h-3 text-emerald-400" /> Speaking
        </Badge>
      );
    }

    if (participant.isMuted) {
      return (
        <Badge variant="outline" size="sm">
          <MicOff className="w-3 h-3 text-slate-500" /> Muted
        </Badge>
      );
    }

    return (
      <Badge variant="blue" size="sm">
        <Mic className="w-3 h-3 text-blue-400" /> Listening
      </Badge>
    );
  };

  return (
    <div
      className={cn(
        "glass-card rounded-2xl p-5 relative overflow-hidden flex flex-col justify-between border transition-all",
        isAI
          ? isGenerating
            ? "border-amber-500/60 ring-2 ring-amber-500/30 shadow-lg shadow-amber-500/10"
            : participant.personaId === "dost"
            ? "border-purple-500/20 opacity-90"
            : "border-pink-500/20 opacity-90"
          : participant.isSpeaking
          ? "border-emerald-500/60 ring-2 ring-emerald-500/30 shadow-lg"
          : "border-slate-800 hover:border-slate-700"
      )}
    >
      {/* Background ambient accent for speaking or AI agents */}
      {participant.isSpeaking && (
        <div className="absolute inset-0 bg-emerald-500/5 pointer-events-none" />
      )}
      {isGenerating && (
        <div className="absolute inset-0 bg-amber-500/5 pointer-events-none" />
      )}

      {/* Top row: Role and State */}
      <div className="flex items-center justify-between z-10">
        <div className="flex items-center gap-1.5">
          {isAI ? (
            <Badge
              variant={participant.personaId === "dost" ? "purple" : "pink"}
              size="sm"
            >
              <Sparkles className="w-3 h-3" />
              AI Persona
            </Badge>
          ) : (
            <Badge variant="default" size="sm">
              <User className="w-3 h-3 text-slate-400" />
              {participant.isLocal ? "You (Human)" : "Human"}
            </Badge>
          )}
        </div>

        <div>{renderStateBadge()}</div>
      </div>

      {/* Center avatar & identity */}
      <div className="my-5 flex flex-col items-center text-center z-10">
        <div
          className={cn(
            "w-16 h-16 rounded-2xl flex items-center justify-center text-xl font-bold mb-3 shadow-lg transition-transform",
            participant.avatarBg,
            participant.isSpeaking && "scale-105 ring-2 ring-emerald-400 ring-offset-2 ring-offset-slate-950",
            isGenerating && "scale-105 ring-2 ring-amber-400 ring-offset-2 ring-offset-slate-950 animate-pulse",
            isAI && !isGenerating && "ring-1 ring-purple-500/20"
          )}
        >
          {isAI ? (
            <Sparkles className="w-7 h-7 text-white" />
          ) : (
            participant.name.slice(0, 2).toUpperCase()
          )}
        </div>

        <h3 className="text-base font-semibold text-white tracking-tight flex items-center gap-1.5">
          {participant.name}
          {participant.isLocal && (
            <span className="text-[10px] text-slate-400 font-normal">(You)</span>
          )}
        </h3>

        <p className={cn(
          "text-xs mt-1 font-mono px-2 py-0.5 rounded border",
          isGenerating
            ? "text-amber-300 font-semibold bg-amber-950/40 border-amber-800/60 animate-pulse"
            : "text-slate-400 bg-slate-900/60 border-slate-800/60"
        )}>
          {participant.badgeText || (isAI ? "LLM STANDBY / Audio STANDBY" : "")}
        </p>

        {isAI ? (
          <p className="text-[11px] text-slate-400 mt-1">
            {participant.personaId === "dost"
              ? "Male · Friendly Hindi/Hinglish companion"
              : "Female · Empathetic Hindi/Hinglish guide"}
          </p>
        ) : (
          <p className="text-[11px] text-slate-500 font-mono mt-1 px-2 py-0.5 rounded bg-slate-900/60 border border-slate-800/40">
            {participant.isMuted ? "Microphone Off" : "Microphone On"}
          </p>
        )}
      </div>

      {/* Bottom meta row */}
      <div className="pt-3 border-t border-slate-800/60 flex items-center justify-between text-xs text-slate-500 z-10">
        <span>{isAI ? (participant.personaId === "dost" ? "AI Dost" : participant.personaId === "sathi" ? "AI Sathi" : "AI Agent") : "Human"}</span>
        <div className="flex items-center gap-1 text-slate-500">
          {isAI ? (
            <span className={cn(
              "text-[11px] font-mono",
              isGenerating ? "text-amber-400 font-semibold" : "text-emerald-400"
            )}>
              {isGenerating ? "● Speaking" : "● Ready"}
            </span>
          ) : participant.isMuted ? (
            <span className="text-slate-500 flex items-center gap-1">
              <MicOff className="w-3.5 h-3.5 text-slate-500" /> Muted
            </span>
          ) : (
            <span className="text-emerald-400 flex items-center gap-1 font-medium">
              <Mic className="w-3.5 h-3.5 text-emerald-400" /> Mic Active
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
