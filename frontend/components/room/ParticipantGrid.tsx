"use client";

import React from "react";
import { ParticipantCard } from "./ParticipantCard";
import { ParticipantUI } from "@/types";
import { useLiveKit } from "@/hooks/LiveKitContext";
import { buildParticipantGridEntries } from "@/lib/participantClassification";

export const ParticipantGrid: React.FC = () => {
  const { participants, connectionState, llmStatus, activeGeneratingBot } = useLiveKit();
  const isConnected = connectionState === "CONNECTED";

  const isDostGenerating =
    (llmStatus === "GENERATING" || llmStatus === "STREAMING") && activeGeneratingBot === "DOST";
  const isSathiGenerating =
    (llmStatus === "GENERATING" || llmStatus === "STREAMING") && activeGeneratingBot === "SATHI";

  // Standby AI slots only while a live room is connected (never fabricate offline presence).
  const dynamicAiPlaceholders: ParticipantUI[] = [
    {
      id: "roxstar-dost",
      name: "Roxstar AI Dost",
      role: "AI_AGENT",
      personaId: "dost",
      gender: "male",
      avatarBg: "bg-gradient-to-tr from-purple-600 to-indigo-700 text-white",
      badgeText: isDostGenerating ? "Responding…" : "Standby",
      mediaState: isDostGenerating ? "SPEAKING" : "IDLE",
      isMuted: false,
      isSpeaking: isDostGenerating,
      isLocal: false,
      isStaticPlaceholder: true,
    },
    {
      id: "roxstar-sathi",
      name: "Roxstar AI Sathi",
      role: "AI_AGENT",
      personaId: "sathi",
      gender: "female",
      avatarBg: "bg-gradient-to-tr from-pink-600 to-rose-600 text-white",
      badgeText: isSathiGenerating ? "Responding…" : "Standby",
      mediaState: isSathiGenerating ? "SPEAKING" : "IDLE",
      isMuted: false,
      isSpeaking: isSathiGenerating,
      isLocal: false,
      isStaticPlaceholder: true,
    },
  ];

  const liveWithGenerating = participants.map((p) => {
    if (p.role !== "AI_AGENT") return p;
    const generating =
      (p.personaId === "dost" && isDostGenerating) ||
      (p.personaId === "sathi" && isSathiGenerating);
    if (!generating) return p;
    return {
      ...p,
      badgeText: "Responding…",
      mediaState: "SPEAKING" as const,
      isSpeaking: true,
    };
  });

  const { humans, ai, humanCount, aiCount } = buildParticipantGridEntries(
    liveWithGenerating,
    isConnected ? dynamicAiPlaceholders : []
  );

  const gridParticipants = isConnected ? [...humans, ...ai] : [];

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1 gap-2">
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
          Room Participants
        </h2>
        <span className="text-[11px] text-slate-500 font-mono truncate">
          {isConnected
            ? `${humanCount} human${humanCount === 1 ? "" : "s"}${
                aiCount > 0 ? ` + ${aiCount} AI` : ""
              }`
            : "Disconnected · Join room to start"}
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4">
        {gridParticipants.map((p) => (
          <ParticipantCard key={p.id} participant={p} />
        ))}

        {!isConnected && (
          <div className="glass-card rounded-2xl p-6 flex flex-col items-center justify-center text-center border border-dashed border-slate-800 col-span-1 sm:col-span-2 xl:col-span-4">
            <p className="text-sm font-medium text-slate-300">No participants connected</p>
            <p className="text-xs text-slate-500 mt-1 max-w-md">
              Choose a display name and click <strong>Join Room</strong> in the control bar. AI
              Dost and AI Sathi appear when the live room is connected.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
