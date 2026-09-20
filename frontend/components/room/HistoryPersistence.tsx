"use client";

import { useEffect, useRef } from "react";
import { useLiveKit } from "@/hooks/LiveKitContext";
import { enrichHistoryMessage, persistCompletedTurn } from "@/lib/chatHistory";

/**
 * Persists completed voice/text/AI transcript turns to localStorage
 * for Chat History / Analytics. Skips partial STT; dedupes by turn id.
 * Enriches with orchestration / latency when those arrive later.
 */
export function HistoryPersistence() {
  const { transcripts, roomName, connectionState } = useLiveKit();
  const seen = useRef(new Set<string>());

  useEffect(() => {
    if (!roomName || connectionState === "DISCONNECTED") return;

    for (const t of transcripts) {
      if (!t.isFinal) continue;
      const id = t.id;
      if (!id) continue;
      // Text-chat turns start as turn-txt-* then get rewritten to the
      // orchestrator turn_id — wait for the stable id to avoid duplicates.
      if (id.startsWith("turn-txt-") && !t.orchestration) continue;

      if (!seen.current.has(id)) {
        seen.current.add(id);

        const source =
          t.speakerId?.startsWith("ai_") || t.speakerName?.toLowerCase().includes("roxstar ai")
            ? ("ai" as const)
            : id.startsWith("turn-txt")
              ? ("text" as const)
              : ("voice" as const);

        persistCompletedTurn({
          id,
          roomId: roomName,
          speakerId: t.speakerId || "",
          speakerName: t.speakerName || t.speakerId || "Speaker",
          text: t.text || "",
          isFinal: true,
          source,
          timestamp: new Date().toISOString(),
          latencyMs: t.latencyMs,
          shouldRespond: t.orchestration?.shouldRespond,
          selectedBot: t.orchestration?.selectedBot,
        });
      } else if (t.orchestration || typeof t.latencyMs === "number") {
        enrichHistoryMessage({
          id,
          roomId: roomName,
          latencyMs: t.latencyMs,
          shouldRespond: t.orchestration?.shouldRespond,
          selectedBot: t.orchestration?.selectedBot,
        });
      }
    }
  }, [transcripts, roomName, connectionState]);

  // Reset in-memory dedupe when leaving a room so a later rejoin still
  // relies on durable id checks in localStorage (no duplicate rows).
  useEffect(() => {
    if (connectionState === "DISCONNECTED") {
      seen.current = new Set();
    }
  }, [connectionState]);

  return null;
}
