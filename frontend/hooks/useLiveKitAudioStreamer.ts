"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { STTState, LiveKitTranscriptEvent } from "@/types";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

interface UseLiveKitAudioStreamerProps {
  mediaStreamTrack: MediaStreamTrack | null;
  sttToken: string | null;
  isMicEnabled: boolean;
  onTranscript: (event: LiveKitTranscriptEvent) => void;
  addEvent: (type: string, message: string, level?: "info" | "warning" | "success" | "error") => void;
}

export function useLiveKitAudioStreamer({
  mediaStreamTrack,
  sttToken,
  isMicEnabled,
  onTranscript,
  addEvent,
}: UseLiveKitAudioStreamerProps) {
  const [sttState, setSttState] = useState<STTState>("IDLE");
  const [latestLatencyMs, setLatestLatencyMs] = useState<number | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  const isCleaningUpRef = useRef<boolean>(false);

  // Derive WebSocket target URL safely without exposing secrets
  const getWsUrl = useCallback((token: string) => {
    let base = BACKEND_URL.replace(/^http/, "ws");
    // Redact token from logs
    return `${base}/api/v1/stt/stream?token=${encodeURIComponent(token)}`;
  }, []);

  // Teardown Web Audio Worklet resources cleanly
  const cleanupAudioPipeline = useCallback(() => {
    if (sourceNodeRef.current) {
      try {
        sourceNodeRef.current.disconnect();
      } catch {}
      sourceNodeRef.current = null;
    }
    if (workletNodeRef.current) {
      try {
        workletNodeRef.current.port.onmessage = null;
        workletNodeRef.current.disconnect();
      } catch {}
      workletNodeRef.current = null;
    }
    if (audioContextRef.current) {
      try {
        audioContextRef.current.close();
      } catch {}
      audioContextRef.current = null;
    }
  }, []);

  // Teardown WebSocket connection
  const cleanupWebSocket = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      try {
        wsRef.current.onopen = null;
        wsRef.current.onmessage = null;
        wsRef.current.onerror = null;
        wsRef.current.onclose = null;
        wsRef.current.close();
      } catch {}
      wsRef.current = null;
    }
  }, []);

  // Initialize and stream audio
  useEffect(() => {
    if (!sttToken || !mediaStreamTrack) {
      setSttState("IDLE");
      cleanupAudioPipeline();
      cleanupWebSocket();
      return;
    }

    isCleaningUpRef.current = false;
    let isSubscribed = true;

    async function initAudioAndSocket() {
      cleanupAudioPipeline();
      cleanupWebSocket();

      setSttState("CONNECTING");

      // 1. Establish STT WebSocket connection
      const wsUrl = getWsUrl(sttToken!);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.binaryType = "arraybuffer";

      ws.onopen = () => {
        if (!isSubscribed) return;
        reconnectAttemptsRef.current = 0;
        // State transitions to ACTIVE once initial ack arrives
      };

      ws.onmessage = (event) => {
        if (!isSubscribed) return;
        try {
          const data = JSON.parse(event.data);

          if (data.type === "stt.connected") {
            setSttState("ACTIVE");
            addEvent("STT_CONNECTED", `STT connected (${data.provider || "sarvam"})`, "success");
            return;
          }

          if (data.type === "stt.error") {
            if (data.error_code === "CONFIGURATION_ERROR") {
              setSttState("DISABLED");
              addEvent("STT_DISABLED", data.message || "STT disabled by configuration", "warning");
            } else {
              setSttState("ERROR");
              addEvent("STT_ERROR", data.message || "STT server error", "error");
            }
            return;
          }

          // Transcript turn (partial or final)
          if (data.status === "partial" || data.status === "final") {
            if (data.latency_ms) {
              setLatestLatencyMs(data.latency_ms);
            }
            onTranscript(data);
          }
        } catch (e) {
          console.warn("Failed to parse STT message:", e);
        }
      };

      ws.onerror = () => {
        if (!isSubscribed || isCleaningUpRef.current) return;
        setSttState("ERROR");
        addEvent("STT_ERROR", "STT WebSocket transport error", "error");
      };

      ws.onclose = (ev) => {
        if (!isSubscribed || isCleaningUpRef.current) return;
        if (ev.code === 4403) {
          setSttState("ERROR");
          addEvent("STT_AUTH_FAILED", "STT session authentication rejected (4403)", "error");
          return;
        }

        // Handle auto-reconnect if mic remains active
        if (isMicEnabled && reconnectAttemptsRef.current < 5) {
          reconnectAttemptsRef.current += 1;
          const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 10000);
          setSttState("RECONNECTING");
          addEvent("STT_RECONNECTING", `STT disconnected. Retrying in ${delay}ms...`, "warning");
          reconnectTimeoutRef.current = setTimeout(() => {
            if (isSubscribed && !isCleaningUpRef.current) {
              initAudioAndSocket();
            }
          }, delay);
        } else {
          setSttState("IDLE");
        }
      };

      // 2. Set up Web Audio Worklet resampler (Hardware rate -> 16,000 Hz linear PCM S16LE)
      try {
        const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
        audioContextRef.current = audioCtx;

        await audioCtx.audioWorklet.addModule("/audio-worklet/stt-resampler-processor.js");

        if (!isSubscribed || !mediaStreamTrack) return;

        const mediaStream = new MediaStream([mediaStreamTrack]);
        const sourceNode = audioCtx.createMediaStreamSource(mediaStream);
        sourceNodeRef.current = sourceNode;

        const workletNode = new AudioWorkletNode(audioCtx, "stt-resampler-processor");
        workletNodeRef.current = workletNode;

        // Ingest downsampled 16kHz PCM chunks and stream to backend WebSocket
        workletNode.port.onmessage = (msgEvent) => {
          if (
            wsRef.current &&
            wsRef.current.readyState === WebSocket.OPEN &&
            isMicEnabled &&
            msgEvent.data
          ) {
            wsRef.current.send(msgEvent.data);
          }
        };

        sourceNode.connect(workletNode);

        if (audioCtx.state === "suspended") {
          await audioCtx.resume();
        }
      } catch (audioErr: any) {
        console.error("Failed to initialize AudioWorklet STT resampler:", audioErr);
        addEvent("AUDIO_RESAMPLER_ERROR", "Could not initialize AudioWorklet", "error");
        setSttState("ERROR");
      }
    }

    initAudioAndSocket();

    return () => {
      isSubscribed = false;
      isCleaningUpRef.current = true;
      cleanupAudioPipeline();
      cleanupWebSocket();
    };
  }, [
    mediaStreamTrack,
    sttToken,
    isMicEnabled,
    getWsUrl,
    onTranscript,
    addEvent,
    cleanupAudioPipeline,
    cleanupWebSocket,
  ]);

  return {
    sttState,
    latestLatencyMs,
  };
}
