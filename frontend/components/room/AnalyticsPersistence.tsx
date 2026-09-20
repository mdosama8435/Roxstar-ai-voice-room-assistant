"use client";

import { useEffect, useRef } from "react";
import { useLiveKit } from "@/hooks/LiveKitContext";
import { recordPipelineEvent, TRACKED_PIPELINE_TYPES } from "@/lib/analytics";

/**
 * Persists safe pipeline event-log entries for Analytics.
 * Dedupes by event id; never stores audio, tokens, or secrets.
 */
export function AnalyticsPersistence() {
  const { eventLog, roomName, connectionState } = useLiveKit();
  const seen = useRef(new Set<string>());

  useEffect(() => {
    if (!roomName || connectionState === "DISCONNECTED") return;

    for (const entry of eventLog) {
      if (!entry?.id || seen.current.has(entry.id)) continue;
      if (!TRACKED_PIPELINE_TYPES.has(entry.type)) continue;
      seen.current.add(entry.id);
      recordPipelineEvent({
        id: entry.id,
        roomId: roomName,
        type: entry.type,
        timestamp: entry.timestamp || new Date().toISOString(),
      });
    }
  }, [eventLog, roomName, connectionState]);

  useEffect(() => {
    if (connectionState === "DISCONNECTED") {
      seen.current = new Set();
    }
  }, [connectionState]);

  return null;
}
