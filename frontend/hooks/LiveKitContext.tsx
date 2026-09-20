"use client";

import React, { createContext, useContext } from "react";
import { useLiveKitRoom } from "./useLiveKitRoom";

type LiveKitContextType = ReturnType<typeof useLiveKitRoom>;

const LiveKitContext = createContext<LiveKitContextType | null>(null);

export const LiveKitProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const livekit = useLiveKitRoom();
  return (
    <LiveKitContext.Provider value={livekit}>
      {children}
    </LiveKitContext.Provider>
  );
};

export const useLiveKit = (): LiveKitContextType => {
  const context = useContext(LiveKitContext);
  if (!context) {
    throw new Error("useLiveKit must be used within a LiveKitProvider");
  }
  return context;
};
