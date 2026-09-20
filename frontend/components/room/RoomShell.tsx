"use client";

import React from "react";
import { ParticipantGrid } from "./ParticipantGrid";
import { VoiceVisualizer } from "./VoiceVisualizer";
import { ConversationPanel } from "./ConversationPanel";
import { RoomControls } from "./RoomControls";
import { HistoryPersistence } from "./HistoryPersistence";
import { AnalyticsPersistence } from "./AnalyticsPersistence";
import { RoomContextCard } from "../intelligence/RoomContextCard";
import { SpeakerMemoryCard } from "../intelligence/SpeakerMemoryCard";
import { BotRoutingCard } from "../intelligence/BotRoutingCard";
import { PipelineCard } from "../intelligence/PipelineCard";

export const RoomShell: React.FC = () => {
  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      <HistoryPersistence />
      <AnalyticsPersistence />
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 flex flex-col p-6 space-y-4 overflow-y-auto">
          <ParticipantGrid />
          <VoiceVisualizer />
          <ConversationPanel />
        </div>

        <aside className="w-84 xl:w-96 h-full flex-shrink-0 glass-panel border-l border-slate-800/80 p-4 space-y-4 overflow-y-auto z-10 hidden lg:block">
          <div className="flex items-center justify-between pb-1">
            <h2 className="text-xs font-bold text-slate-300 uppercase tracking-wider">
              Room Intelligence
            </h2>
            <span className="text-[10px] text-purple-400 font-mono px-1.5 py-0.5 rounded bg-purple-950/60 border border-purple-800/40">
              Live
            </span>
          </div>

          <RoomContextCard />
          <SpeakerMemoryCard />
          <BotRoutingCard />
          <PipelineCard />
        </aside>
      </div>

      <RoomControls />
    </div>
  );
};
