"use client";

import React from "react";
import { Mic, MicOff, Radio, Volume2 } from "lucide-react";
import { useLiveKit } from "@/hooks/LiveKitContext";

export const VoiceVisualizer: React.FC = () => {
  const { connectionState, isMicEnabled, activeSpeakerId, participants } = useLiveKit();
  const isConnected = connectionState === "CONNECTED";

  // Check if anyone is speaking
  const activeSpeaker = participants.find((p) => p.id === activeSpeakerId);

  return (
    <div className="glass-panel-subtle rounded-xl p-3 flex items-center justify-between border border-slate-800/80">
      <div className="flex items-center gap-2.5">
        <div
          className={`w-7 h-7 rounded-lg border flex items-center justify-center transition-colors ${
            !isConnected
              ? "bg-slate-900 border-slate-800 text-slate-500"
              : activeSpeaker
              ? "bg-emerald-950/60 border-emerald-800/60 text-emerald-400"
              : isMicEnabled
              ? "bg-purple-950/60 border-purple-800/60 text-purple-400"
              : "bg-slate-900 border-slate-800 text-slate-500"
          }`}
        >
          {!isConnected ? (
            <MicOff className="w-3.5 h-3.5" />
          ) : activeSpeaker ? (
            <Volume2 className="w-3.5 h-3.5 animate-pulse" />
          ) : isMicEnabled ? (
            <Mic className="w-3.5 h-3.5" />
          ) : (
            <MicOff className="w-3.5 h-3.5" />
          )}
        </div>

        <div>
          <p className="text-xs font-medium text-slate-300 flex items-center gap-1.5">
            Real-time LiveKit Audio
            {isConnected && (
              <span className="text-[10px] text-emerald-400 font-mono flex items-center gap-1">
                <Radio className="w-2.5 h-2.5" /> WebRTC Active
              </span>
            )}
          </p>
          <p className="text-[11px] text-slate-500">
            {!isConnected
              ? "Audio pipeline inactive • Connect to LiveKit room to publish audio"
              : activeSpeaker
              ? `${activeSpeaker.name} is speaking...`
              : isMicEnabled
              ? "Microphone is on • Listening for audio"
              : "Microphone is muted"}
          </p>
        </div>
      </div>

      {/* Honest level indicators based on real active speaker state */}
      <div className="flex items-center gap-1 h-5 px-3 py-1 bg-slate-950/60 rounded-md border border-slate-800/60">
        {[...Array(16)].map((_, i) => (
          <div
            key={i}
            className={`w-1 rounded-full transition-all ${
              activeSpeaker
                ? "h-3.5 bg-emerald-500"
                : isMicEnabled && isConnected
                ? "h-2 bg-purple-500/60"
                : "h-1 bg-slate-700/50"
            }`}
          />
        ))}
      </div>
    </div>
  );
};
