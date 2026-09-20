"use client";

import React from "react";
import { Brain, Info, User } from "lucide-react";
import { useLiveKit } from "@/hooks/LiveKitContext";

export const SpeakerMemoryCard: React.FC = () => {
  const { participants, roomContextState, connectionState } = useLiveKit();
  const humans = participants.filter((p) => p.role !== "AI_AGENT");
  const facts = roomContextState?.facts || {};

  const profiles = humans
    .map((h) => ({
      name: h.name,
      facts: facts[h.name] || facts[h.id] || [],
    }))
    .filter((p) => p.facts.length > 0);

  return (
    <div className="glass-card rounded-xl p-4 space-y-3 border border-slate-800">
      <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-300 uppercase tracking-wider">
          <Brain className="w-4 h-4 text-pink-400" />
          <span>Speaker Memory</span>
        </div>
        <span className="text-[10px] text-slate-500 font-mono">session</span>
      </div>

      {profiles.length === 0 ? (
        <div className="py-4 text-center space-y-1">
          <p className="text-xs text-slate-500 italic">
            {connectionState === "CONNECTED"
              ? "No speaker memory yet"
              : "Not connected"}
          </p>
          <p className="text-[11px] text-slate-600 flex items-center justify-center gap-1">
            <Info className="w-3 h-3" />
            Facts extracted during dialogue will appear here
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {profiles.map((profile) => (
            <div key={profile.name} className="space-y-1.5">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-200">
                <User className="w-3.5 h-3.5 text-cyan-400" />
                {profile.name}
              </div>
              <ul className="pl-5 space-y-0.5">
                {profile.facts.map((fact, i) => (
                  <li key={i} className="text-[11px] text-slate-400 list-disc">
                    {fact}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
