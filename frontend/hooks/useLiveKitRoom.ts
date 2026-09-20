"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  Room,
  RoomEvent,
  Track,
  RemoteTrack,
  RemoteTrackPublication,
  RemoteParticipant,
  Participant as LiveKitParticipant,
} from "livekit-client";
import {
  ParticipantUI,
  RoomConnectionState,
  LiveKitChatMessage,
  RoomEventLogEntry,
  MediaState,
  STTState,
  TranscriptTurn,
  LiveKitTranscriptEvent,
  BotRoutingUI,
  RoomContextUI,
  OrchestrationMetadata,
  BotType,
  LLMStatus,
  AIStreamingPreview,
} from "@/types";
import { useLiveKitAudioStreamer } from "./useLiveKitAudioStreamer";
import { classifyLiveKitParticipant } from "@/lib/participantClassification";
import {
  applyCanonicalAiResponse,
  applyStreamingChunk,
} from "@/lib/streamingPreviewState";
import {
  beginSession,
  logLiveKitLifecycle,
  shouldApplyRoomEvent,
} from "@/lib/livekitSessionGuard";
import {
  applyTtsEvent,
  createInitialTtsPipelineState,
  selectPipelineTtsStatus,
  type TTSPipelineStateByBot,
  type TTSPipelineStatus,
} from "@/lib/ttsPipelineState";


const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

interface ConnectOptions {
  roomName: string;
  displayName: string;
}

export function useLiveKitRoom() {
  const [connectionState, setConnectionState] = useState<RoomConnectionState>("IDLE");
  const [roomName, setRoomName] = useState<string>("roxstar-test");
  const [displayName, setDisplayName] = useState<string>("Rahul");
  const [localIdentity, setLocalIdentity] = useState<string>("");
  const [participants, setParticipants] = useState<ParticipantUI[]>([]);
  const [isMicEnabled, setIsMicEnabled] = useState<boolean>(false);
  const [activeSpeakerId, setActiveSpeakerId] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<LiveKitChatMessage[]>([]);
  const [eventLog, setEventLog] = useState<RoomEventLogEntry[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Phase 3A STT Streaming state
  const [sttToken, setSttToken] = useState<string | null>(null);
  const [mediaStreamTrack, setMediaStreamTrack] = useState<MediaStreamTrack | null>(null);
  const [transcripts, setTranscripts] = useState<TranscriptTurn[]>([]);

  // Phase 3B Orchestration States
  const [activeRouting, setActiveRouting] = useState<BotRoutingUI>({
    selectedBot: "NONE",
    reason: "Awaiting speech or text turn",
    confidence: 1.0,
    lockStatus: "IDLE",
  });
  const [roomContextState, setRoomContextState] = useState<RoomContextUI>({
    currentTopic: null,
    activeSpeakerId: null,
    turnCount: 0,
    facts: {},
  });

  // Phase 3C LLM States
  const [llmStatus, setLlmStatus] = useState<LLMStatus>("STANDBY");
  const [activeStreamingPreview, setActiveStreamingPreview] = useState<AIStreamingPreview | null>(null);
  const [activeGeneratingBot, setActiveGeneratingBot] = useState<BotType | null>(null);
  const completedAiRequestIdsRef = useRef<Set<string>>(new Set());

  // Phase 3F.10.2 — TTS pipeline UI from real tts.* DataChannel events
  const [ttsStateByBot, setTtsStateByBot] = useState<TTSPipelineStateByBot>(
    createInitialTtsPipelineState
  );
  const ttsStatus: TTSPipelineStatus = selectPipelineTtsStatus(ttsStateByBot);

  // Browser autoplay may block remote AI/human audio until a user gesture
  const [audioPlaybackBlocked, setAudioPlaybackBlocked] = useState(false);


  // References to maintain persistent room instance and audio elements across renders
  const roomRef = useRef<Room | null>(null);
  const audioElementsRef = useRef<Map<string, HTMLMediaElement>>(new Map());
  /** Bumped on every connect/leave so stale Room events cannot mutate UI. */
  const sessionIdRef = useRef(0);
  /** Monotonic id per Room instance (dev diagnostics only). */
  const roomInstanceSeqRef = useRef(0);

  // Helper to add structured events to the Events tab
  const addEvent = useCallback((type: string, message: string, level: "info" | "warning" | "success" | "error" = "info") => {
    const newEntry: RoomEventLogEntry = {
      id: `evt-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      timestamp: new Date().toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" }),
      type,
      message,
      level,
    };
    setEventLog((prev) => [newEntry, ...prev.slice(0, 49)]); // Keep last 50 events
  }, []);

  // Handle local STT transcripts (in-place partial updates + finalized turn commits)
  const handleTranscript = useCallback(
    (evt: LiveKitTranscriptEvent) => {
      const isLocal = true;
      const speakerName = evt.participant_display_name || displayName;

      if (evt.status === "partial") {
        setTranscripts((prev) => {
          const interimIdx = prev.findIndex(
            (t) => !t.isFinal && t.speakerId === evt.participant_identity
          );
          const updatedTurn: TranscriptTurn = {
            id: `interim-${evt.participant_identity}`,
            speakerId: evt.participant_identity,
            speakerName,
            text: evt.transcript,
            isFinal: false,
            detectedLanguage: evt.detected_language,
            languageConfidence: evt.language_confidence,
            latencyMs: evt.latency_ms,
            timestamp: new Date().toLocaleTimeString([], {
              hour12: false,
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            }),
            isLocal,
          };

          if (interimIdx !== -1) {
            const next = [...prev];
            next[interimIdx] = updatedTurn;
            return next;
          }
          return [...prev, updatedTurn];
        });
      } else {
        setTranscripts((prev) => {
          const filtered = prev.filter(
            (t) => !(t.speakerId === evt.participant_identity && !t.isFinal)
          );
          const finalTurn: TranscriptTurn = {
            id: evt.event_id || `turn-${Date.now()}`,
            speakerId: evt.participant_identity,
            speakerName,
            text: evt.transcript,
            isFinal: true,
            detectedLanguage: evt.detected_language,
            languageConfidence: evt.language_confidence,
            latencyMs: evt.latency_ms,
            timestamp: new Date().toLocaleTimeString([], {
              hour12: false,
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            }),
            isLocal,
          };
          return [...filtered, finalTurn];
        });

        addEvent(
          "STT_FINAL",
          `${speakerName}: "${evt.transcript}"${evt.latency_ms ? ` (${evt.latency_ms}ms)` : ""}`,
          "success"
        );
      }
    },
    [displayName, addEvent]
  );

  // Helper to map a LiveKit Participant to ParticipantUI (human vs AI)
  const mapParticipantToUI = useCallback(
    (p: LiveKitParticipant, isLocal: boolean, activeSpeakers: LiveKitParticipant[] = []): ParticipantUI => {
      const isSpeaking = activeSpeakers.some((s) => s.identity === p.identity);
      const isMuted = !p.isMicrophoneEnabled;

      let mediaState: MediaState = "IDLE";
      if (isSpeaking) {
        mediaState = "SPEAKING";
      } else if (!isMuted) {
        mediaState = "LISTENING";
      } else {
        mediaState = "MUTED";
      }

      const classified = classifyLiveKitParticipant({
        identity: p.identity,
        name: p.name,
        kind: (p as { kind?: string | number }).kind,
        isLocal,
      });

      return {
        id: p.identity,
        name: classified.displayName,
        role: classified.role,
        personaId: classified.personaId,
        gender: classified.gender,
        avatarBg: classified.avatarBg,
        badgeText: classified.badgeText,
        mediaState: classified.role === "AI_AGENT" ? "IDLE" : mediaState,
        isMuted: classified.role === "AI_AGENT" ? false : isMuted,
        isSpeaking: classified.role === "AI_AGENT" ? false : isSpeaking,
        isLocal,
        isStaticPlaceholder: false,
      };
    },
    [displayName]
  );

  // Synchronize entire participant list from the active LiveKit room
  const syncParticipants = useCallback(
    (currentRoom: Room) => {
      const activeSpeakers = currentRoom.activeSpeakers;
      const list: ParticipantUI[] = [];

      // Local participant
      if (currentRoom.localParticipant) {
        list.push(mapParticipantToUI(currentRoom.localParticipant, true, activeSpeakers));
      }

      // Remote participants
      currentRoom.remoteParticipants.forEach((remoteP) => {
        list.push(mapParticipantToUI(remoteP, false, activeSpeakers));
      });

      setParticipants(list);
    },
    [mapParticipantToUI]
  );

  /** Tear down a Room without letting its events mutate current UI. */
  const teardownRoomInstance = useCallback(async (room: Room | null, reason: string) => {
    if (!room) return;
    logLiveKitLifecycle({
      event: "teardown",
      sessionId: sessionIdRef.current,
      detail: reason,
    });
    try {
      await room.disconnect();
    } catch {
      /* disconnect is best-effort during supersede/leave */
    }
    try {
      room.removeAllListeners();
    } catch {
      /* EventEmitter cleanup */
    }
  }, []);

  // Connect to LiveKit Room
  const connect = useCallback(
    async ({ roomName: targetRoom, displayName: targetName }: ConnectOptions) => {
      // Invalidate any prior in-flight connect / stale Room before starting a new session.
      const sessionId = beginSession(sessionIdRef.current);
      sessionIdRef.current = sessionId;
      logLiveKitLifecycle({ event: "session_begin", sessionId, detail: "connect" });

      const previousRoom = roomRef.current;
      roomRef.current = null;
      await teardownRoomInstance(previousRoom, "superseded_by_new_connect");

      if (sessionId !== sessionIdRef.current) {
        logLiveKitLifecycle({ event: "session_superseded", sessionId, detail: "after_prior_teardown" });
        return;
      }

      setErrorMessage(null);
      setConnectionState("CONNECTING");
      addEvent("ROOM_CONNECTING", `Requesting access token for ${targetName}...`, "info");

      // Step 1: Fetch LiveKit access token from backend
      if (process.env.NODE_ENV !== "production") {
        console.log(`[useLiveKitRoom] Starting token request to ${BACKEND_URL}/api/v1/livekit/token for room: "${targetRoom}"`);
      }

      let tokenRes: Response;
      try {
        tokenRes = await fetch(`${BACKEND_URL}/api/v1/livekit/token`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            room_name: targetRoom.trim(),
            display_name: targetName.trim(),
          }),
        });
      } catch (fetchErr: any) {
        if (sessionId !== sessionIdRef.current) return;
        if (process.env.NODE_ENV !== "production") {
          console.warn("[useLiveKitRoom] Category: Backend unreachable / network failure", fetchErr);
        }
        const unreachableMsg = `Cannot reach backend at ${BACKEND_URL}. Make sure the FastAPI server is running.`;
        setErrorMessage(unreachableMsg);
        setConnectionState("ERROR");
        addEvent("BACKEND_UNREACHABLE", unreachableMsg, "error");
        return;
      }

      if (sessionId !== sessionIdRef.current) {
        logLiveKitLifecycle({ event: "session_superseded", sessionId, detail: "after_token_fetch" });
        return;
      }

      if (process.env.NODE_ENV !== "production") {
        console.log(`[useLiveKitRoom] HTTP status: ${tokenRes.status} from ${BACKEND_URL}`);
      }

      if (!tokenRes.ok) {
        let errorDetail = "";
        try {
          const errData = await tokenRes.json();
          errorDetail = errData.detail || "";
        } catch {
          // Non-JSON response body
        }

        let userMsg = "";
        if (tokenRes.status === 503) {
          userMsg = errorDetail || "LiveKit is not configured on the backend.";
          if (process.env.NODE_ENV !== "production") {
            console.warn(`[useLiveKitRoom] Category: HTTP 503 - LiveKit unconfigured: ${userMsg}`);
          }
          addEvent("LIVEKIT_NOT_CONFIGURED", userMsg, "error");
        } else if (tokenRes.status >= 400 && tokenRes.status < 500) {
          userMsg = errorDetail || "Invalid room or participant information.";
          if (process.env.NODE_ENV !== "production") {
            console.warn(`[useLiveKitRoom] Category: HTTP ${tokenRes.status} - Client error: ${userMsg}`);
          }
          addEvent("INVALID_REQUEST", userMsg, "error");
        } else if (tokenRes.status >= 500) {
          userMsg = errorDetail || "Backend LiveKit token service failed.";
          if (process.env.NODE_ENV !== "production") {
            console.error(`[useLiveKitRoom] Category: HTTP ${tokenRes.status} - Server error: ${userMsg}`);
          }
          addEvent("BACKEND_SERVER_ERROR", userMsg, "error");
        } else {
          userMsg = `Token request failed with status ${tokenRes.status}`;
          addEvent("TOKEN_ERROR", userMsg, "error");
        }

        if (sessionId !== sessionIdRef.current) return;
        setErrorMessage(userMsg);
        setConnectionState("ERROR");
        return;
      }

      // Step 2: Validate token response format
      let tokenData: any;
      try {
        tokenData = await tokenRes.json();
        if (
          !tokenData ||
          typeof tokenData.token !== "string" ||
          typeof tokenData.server_url !== "string" ||
          typeof tokenData.participant_identity !== "string"
        ) {
          throw new Error("Missing required token payload fields");
        }
      } catch (parseErr: any) {
        if (sessionId !== sessionIdRef.current) return;
        if (process.env.NODE_ENV !== "production") {
          console.error("[useLiveKitRoom] Category: Invalid/malformed response:", parseErr);
        }
        const malformedMsg = "Backend returned an invalid LiveKit token response.";
        setErrorMessage(malformedMsg);
        setConnectionState("ERROR");
        addEvent("MALFORMED_RESPONSE", malformedMsg, "error");
        return;
      }

      if (sessionId !== sessionIdRef.current) {
        logLiveKitLifecycle({ event: "session_superseded", sessionId, detail: "after_token_parse" });
        return;
      }

      setLocalIdentity(tokenData.participant_identity);
      setRoomName(targetRoom);
      setDisplayName(targetName);
      setSttToken(tokenData.stt_token || null);

      try {
        // Step 3: Initialize LiveKit Room instance
        const room = new Room({
          adaptiveStream: true,
          dynacast: true,
          audioCaptureDefaults: {
            autoGainControl: true,
            echoCancellation: true,
            noiseSuppression: true,
          },
        });

        const roomInstanceId = ++roomInstanceSeqRef.current;
        roomRef.current = room;
        logLiveKitLifecycle({
          event: "room_created",
          sessionId,
          roomInstanceId,
        });

        const applyIfLive = (eventName: string): boolean => {
          const ok = shouldApplyRoomEvent({
            activeSessionId: sessionIdRef.current,
            eventSessionId: sessionId,
            activeRoom: roomRef.current,
            eventRoom: room,
          });
          if (!ok) {
            logLiveKitLifecycle({
              event: "stale_event_ignored",
              sessionId,
              roomInstanceId,
              detail: eventName,
            });
          }
          return ok;
        };

        // Step 3: Register Room Event Listeners (gated to this session + room instance)
        room.on(RoomEvent.Connected, () => {
          if (!applyIfLive("Connected")) return;
          setConnectionState("CONNECTED");
          addEvent("CONNECTED", `Connected to LiveKit room '${targetRoom}'`, "success");
          syncParticipants(room);
          logLiveKitLifecycle({ event: "room_connected", sessionId, roomInstanceId });
        });

        room.on(RoomEvent.ParticipantConnected, (p: RemoteParticipant) => {
          if (!applyIfLive("ParticipantConnected")) return;
          addEvent("PARTICIPANT_JOINED", `${p.name || p.identity} joined the room`, "info");
          syncParticipants(room);
        });

        room.on(RoomEvent.ParticipantDisconnected, (p: RemoteParticipant) => {
          if (!applyIfLive("ParticipantDisconnected")) return;
          addEvent("PARTICIPANT_LEFT", `${p.name || p.identity} left the room`, "warning");
          syncParticipants(room);
        });

        room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack, pub: RemoteTrackPublication, p: RemoteParticipant) => {
          if (!applyIfLive("TrackSubscribed")) return;
          if (track.kind === Track.Kind.Audio) {
            // Attach audio element for playback
            const element = track.attach();
            element.id = `audio-${p.identity}-${track.sid}`;
            audioElementsRef.current.set(element.id, element);
            addEvent("AUDIO_SUBSCRIBED", `Subscribed to audio from ${p.name || p.identity}`, "info");

            // Handle browser autoplay policy — surface unlock CTA on failure
            room.startAudio().then(() => {
              setAudioPlaybackBlocked(false);
            }).catch(() => {
              setAudioPlaybackBlocked(true);
              addEvent(
                "AUDIO_BLOCKED",
                "Browser blocked autoplay — click Enable Audio to hear the room",
                "warning"
              );
            });
          }
          syncParticipants(room);
        });

        room.on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack, pub: RemoteTrackPublication, p: RemoteParticipant) => {
          if (!applyIfLive("TrackUnsubscribed")) return;
          if (track.kind === Track.Kind.Audio) {
            track.detach();
            const elementId = `audio-${p.identity}-${track.sid}`;
            audioElementsRef.current.delete(elementId);
          }
          syncParticipants(room);
        });

        room.on(RoomEvent.TrackMuted, (pub, p) => {
          if (!applyIfLive("TrackMuted")) return;
          addEvent("TRACK_MUTED", `${p.name || p.identity} muted microphone`, "info");
          syncParticipants(room);
        });

        room.on(RoomEvent.TrackUnmuted, (pub, p) => {
          if (!applyIfLive("TrackUnmuted")) return;
          addEvent("TRACK_UNMUTED", `${p.name || p.identity} unmuted microphone`, "info");
          syncParticipants(room);
        });

        room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
          if (!applyIfLive("ActiveSpeakersChanged")) return;
          if (speakers.length > 0) {
            setActiveSpeakerId(speakers[0].identity);
          } else {
            setActiveSpeakerId(null);
          }
          syncParticipants(room);
        });

        room.on(RoomEvent.LocalTrackPublished, (pub) => {
          if (!applyIfLive("LocalTrackPublished")) return;
          if (pub.kind === Track.Kind.Audio && (pub.track as any)?.mediaStreamTrack) {
            setMediaStreamTrack((pub.track as any).mediaStreamTrack);
          }
        });

        room.on(RoomEvent.LocalTrackUnpublished, (pub) => {
          if (!applyIfLive("LocalTrackUnpublished")) return;
          if (pub.kind === Track.Kind.Audio) {
            setMediaStreamTrack(null);
          }
        });

        room.on(RoomEvent.Reconnecting, () => {
          if (!applyIfLive("Reconnecting")) return;
          setConnectionState("RECONNECTING");
          addEvent("RECONNECTING", "Network interrupted. Reconnecting to LiveKit...", "warning");
          logLiveKitLifecycle({ event: "room_reconnect", sessionId, roomInstanceId });
        });

        room.on(RoomEvent.Reconnected, () => {
          if (!applyIfLive("Reconnected")) return;
          setConnectionState("CONNECTED");
          addEvent("RECONNECTED", "Successfully reconnected to LiveKit room", "success");
          syncParticipants(room);
          logLiveKitLifecycle({ event: "room_reconnected", sessionId, roomInstanceId });
        });

        room.on(RoomEvent.Disconnected, () => {
          if (!applyIfLive("Disconnected")) return;
          // Unexpected disconnect (not intentional leave — leave clears roomRef first).
          setConnectionState("DISCONNECTED");
          addEvent("DISCONNECTED", "Disconnected from LiveKit room", "info");
          setParticipants([]);
        });

        // Step 4: Handle LiveKit DataChannel Messages (Text Chat & STT Broadcasts)
        room.on(RoomEvent.DataReceived, (payload: Uint8Array, participant?: RemoteParticipant) => {
          if (!applyIfLive("DataReceived")) return;
          try {
            const decodedStr = new TextDecoder().decode(payload);
            const data = JSON.parse(decodedStr);

            if (data.type === "chat.message" && data.text) {
              const incomingMsg: LiveKitChatMessage = {
                id: data.message_id || `msg-${Date.now()}`,
                senderId: data.sender_id || participant?.identity || "unknown",
                senderName: data.sender_name || participant?.name || "Participant",
                text: data.text,
                timestamp: data.timestamp || new Date().toISOString(),
                isLocal: false,
              };

              setChatMessages((prev) => [...prev, incomingMsg]);
              addEvent("CHAT_MESSAGE", `${incomingMsg.senderName}: ${incomingMsg.text.slice(0, 32)}`, "info");
            } else if (data.type === "transcript.event" && data.transcript) {
              // Remote finalized transcript turn received over DataChannel
              if (data.participant_identity !== tokenData.participant_identity) {
                const remoteTurn: TranscriptTurn = {
                  id: data.event_id || `turn-${Date.now()}`,
                  speakerId: data.participant_identity,
                  speakerName: data.participant_display_name || participant?.name || "Participant",
                  text: data.transcript,
                  isFinal: true,
                  detectedLanguage: data.detected_language,
                  languageConfidence: data.language_confidence,
                  latencyMs: data.latency_ms,
                  timestamp: new Date().toLocaleTimeString([], {
                    hour12: false,
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  }),
                  isLocal: false,
                };
                setTranscripts((prev) => [...prev, remoteTurn]);
                addEvent(
                  "STT_REMOTE",
                  `${remoteTurn.speakerName}: "${data.transcript}"${data.latency_ms ? ` (${data.latency_ms}ms)` : ""}`,
                  "info"
                );
              }
            } else if (data.type === "orchestration.event") {
              const orchMeta: OrchestrationMetadata = {
                decisionId: data.event_id || `orch-${Date.now()}`,
                shouldRespond: Boolean(data.should_respond),
                triggerType: data.trigger_type || "UNKNOWN",
                selectedBot: (data.selected_bot as BotType) || "NONE",
                routingReason: data.routing_reason || "",
                turnLockAcquired: Boolean(data.turn_lock_acquired),
                lockDeferred: Boolean(data.lock_deferred),
                metrics: data.metrics || {},
              };

              // Update matching transcript turn with orchestration metadata
              setTranscripts((prev) => {
                const updated = [...prev];
                // Match by turn_id or match the latest turn from this participant
                const turnIdx = updated.findIndex((t) => t.id === data.turn_id);
                if (turnIdx >= 0) {
                  updated[turnIdx] = { ...updated[turnIdx], orchestration: orchMeta };
                  return updated;
                } else {
                  // If remote speaker turn was finalized without local match, find latest for participant
                  for (let i = updated.length - 1; i >= 0; i--) {
                    if (updated[i].speakerId === data.participant_identity && updated[i].isFinal) {
                      updated[i] = { ...updated[i], orchestration: orchMeta };
                      return updated;
                    }
                  }
                }
                return updated;
              });

              setActiveRouting({
                selectedBot: orchMeta.selectedBot,
                reason: orchMeta.routingReason,
                confidence: 0.95,
                lockStatus: orchMeta.turnLockAcquired ? "ACQUIRED" : orchMeta.lockDeferred ? "BLOCKED" : "IDLE",
                lastTurnId: data.turn_id,
              });

              setRoomContextState((prev) => ({
                ...prev,
                turnCount: prev.turnCount + 1,
                activeSpeakerId: data.participant_identity,
              }));

              addEvent(
                "ORCHESTRATION",
                `${data.participant_display_name || "Speaker"}: [${data.selected_bot}] ${data.should_respond ? "Response Required" : "Silence"} (${data.trigger_type})`,
                data.should_respond ? "success" : "info"
              );
            } else if (data.type === "ai.response.chunk") {
              const botType = (data.bot as BotType) || "DOST";
              let ignored = true;
              let nextBot: BotType | null = null;
              setActiveStreamingPreview((prev) => {
                const result = applyStreamingChunk(
                  prev,
                  completedAiRequestIdsRef.current,
                  {
                    requestId: data.request_id,
                    bot: botType,
                    textDelta: data.text_delta || "",
                    isFinal: Boolean(data.is_final),
                    roomName: data.room_name,
                  }
                );
                ignored = result.ignored;
                nextBot = result.generatingBot;
                return result.ignored ? prev : (result.preview as AIStreamingPreview | null);
              });
              if (!ignored) {
                setLlmStatus("STREAMING");
                setActiveGeneratingBot(nextBot);
              }
            } else if (data.type === "ai.response" && data.text) {
              const botType = (data.bot as BotType) || "DOST";
              let clearGenerating = false;
              setActiveStreamingPreview((prev) => {
                const cleared = applyCanonicalAiResponse(
                  prev,
                  completedAiRequestIdsRef.current,
                  {
                    requestId: data.request_id,
                    bot: botType,
                    roomName: data.room_name,
                    text: data.text,
                  }
                );
                completedAiRequestIdsRef.current = cleared.completedRequestIds;
                clearGenerating = cleared.clearGenerating;
                return cleared.preview as AIStreamingPreview | null;
              });
              if (clearGenerating) {
                setLlmStatus("COMPLETED");
                setActiveGeneratingBot(null);
              }

              const botDisplayName = data.bot_display_name || (botType === "DOST" ? "RoxStar AI Dost" : "RoxStar AI Sathi");

              const aiChatMsg: LiveKitChatMessage = {
                id: data.event_id || `aimsg-${Date.now()}`,
                senderId: botType === "DOST" ? "ai_dost" : "ai_sathi",
                senderName: botDisplayName,
                text: data.text,
                timestamp: data.timestamp || new Date().toISOString(),
                isLocal: false,
                botType: botType,
              };
              setChatMessages((prev) => [...prev, aiChatMsg]);

              const aiTurn: TranscriptTurn = {
                id: data.event_id || `turn-ai-${Date.now()}`,
                speakerId: botType === "DOST" ? "ai_dost" : "ai_sathi",
                speakerName: botDisplayName,
                text: data.text,
                isFinal: true,
                detectedLanguage: "hi",
                latencyMs: data.latency_ms,
                timestamp: new Date().toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" }),
                isLocal: false,
              };
              setTranscripts((prev) => [...prev, aiTurn]);

              addEvent(
                "AI_RESPONSE",
                `${botDisplayName}: "${data.text.slice(0, 48)}..." (${data.latency_ms || 0}ms)`,
                "success"
              );
            } else if (data.type === "tts.event" && data.event_type) {
              setTtsStateByBot((prev) =>
                applyTtsEvent(prev, {
                  event_type: data.event_type,
                  agent_id: data.agent_id,
                  request_id: data.request_id,
                })
              );
              addEvent(
                "TTS",
                `${data.agent_id || "tts"}: ${data.event_type}${
                  data.ttfa_ms != null ? ` (ttfa ${data.ttfa_ms}ms)` : ""
                }`,
                data.event_type === "tts.failed" || data.event_type === "tts.error"
                  ? "error"
                  : data.event_type === "tts.cancelled" || data.event_type === "audio.cancelled"
                  ? "warning"
                  : "info"
              );
            }
          } catch (e) {

            console.warn("Failed to parse incoming DataChannel packet:", e);
          }
        });

        // Step 5: Connect to LiveKit SFU via WebRTC
        logLiveKitLifecycle({ event: "room_connect_start", sessionId, roomInstanceId });
        await room.connect(tokenData.server_url, tokenData.token);

        if (sessionId !== sessionIdRef.current || roomRef.current !== room) {
          logLiveKitLifecycle({
            event: "session_superseded",
            sessionId,
            roomInstanceId,
            detail: "after_room_connect",
          });
          await teardownRoomInstance(room, "stale_after_connect");
          return;
        }

        // Step 6: Attempt microphone publishing & tap track for STT
        try {
          await room.localParticipant.setMicrophoneEnabled(true);
          if (sessionId !== sessionIdRef.current || roomRef.current !== room) {
            await teardownRoomInstance(room, "stale_after_mic");
            return;
          }
          setIsMicEnabled(true);
          addEvent("MIC_PUBLISHED", "Microphone published successfully", "success");

          const micPub = room.localParticipant.getTrackPublication(Track.Source.Microphone);
          if (micPub && micPub.track && (micPub.track as any).mediaStreamTrack) {
            setMediaStreamTrack((micPub.track as any).mediaStreamTrack);
          }
        } catch (micErr: any) {
          if (sessionId !== sessionIdRef.current || roomRef.current !== room) return;
          console.warn("Microphone access failed or denied:", micErr);
          setIsMicEnabled(false);
          setMediaStreamTrack(null);
          addEvent("MIC_DENIED", "Microphone permission denied or unavailable", "warning");
        }

        if (sessionId === sessionIdRef.current && roomRef.current === room) {
          syncParticipants(room);
        }
      } catch (webrtcErr: any) {
        if (sessionId !== sessionIdRef.current) return;
        if (process.env.NODE_ENV !== "production") {
          console.error("[useLiveKitRoom] WebRTC Room connection failure:", webrtcErr);
        }
        const errText = webrtcErr.message || "Failed to establish LiveKit connection.";
        setErrorMessage(errText);
        setConnectionState("ERROR");
        addEvent("CONNECTION_FAILED", errText, "error");
        if (roomRef.current) {
          const failed = roomRef.current;
          roomRef.current = null;
          await teardownRoomInstance(failed, "connect_failed");
        }
      }
    },
    [addEvent, syncParticipants, teardownRoomInstance]
  );

  // Disconnect cleanly — full room-session reset so rejoin has no stale state
  const disconnect = useCallback(async () => {
    const leaveSessionId = beginSession(sessionIdRef.current);
    sessionIdRef.current = leaveSessionId;
    logLiveKitLifecycle({ event: "intentional_leave", sessionId: leaveSessionId });

    const room = roomRef.current;
    roomRef.current = null;

    if (room) {
      addEvent("LEAVING_ROOM", "Leaving LiveKit room...", "info");
      // Detach all audio elements
      audioElementsRef.current.forEach((el) => {
        el.pause();
        el.srcObject = null;
        el.remove();
      });
      audioElementsRef.current.clear();

      try {
        await room.localParticipant?.setMicrophoneEnabled(false);
      } catch {
        /* mic may already be gone */
      }

      await teardownRoomInstance(room, "intentional_leave");
    }
    setConnectionState("IDLE");
    setParticipants([]);
    setIsMicEnabled(false);
    setActiveSpeakerId(null);
    setSttToken(null);
    setMediaStreamTrack(null);
    setTranscripts([]);
    setChatMessages([]);
    setEventLog([]);
    setLocalIdentity("");
    setErrorMessage(null);
    setActiveRouting({
      selectedBot: "NONE",
      reason: "Awaiting speech or text turn",
      confidence: 1.0,
      lockStatus: "IDLE",
    });
    setRoomContextState({
      currentTopic: null,
      activeSpeakerId: null,
      turnCount: 0,
      facts: {},
    });
    setLlmStatus("STANDBY");
    setActiveStreamingPreview(null);
    setActiveGeneratingBot(null);
    setTtsStateByBot(createInitialTtsPipelineState());
    setAudioPlaybackBlocked(false);
    completedAiRequestIdsRef.current = new Set();
    addEvent("ROOM_LEFT", "Disconnected — room state reset", "success");
  }, [addEvent, teardownRoomInstance]);

  const unlockAudio = useCallback(async () => {
    const room = roomRef.current;
    if (!room) return;
    try {
      await room.startAudio();
      setAudioPlaybackBlocked(false);
      addEvent("AUDIO_UNLOCKED", "Audio playback enabled", "success");
    } catch {
      setAudioPlaybackBlocked(true);
      addEvent("AUDIO_BLOCKED", "Audio unlock failed — try clicking Enable Audio again", "warning");
    }
  }, [addEvent]);

  // Toggle Microphone Mute/Unmute
  const toggleMicrophone = useCallback(async () => {
    if (!roomRef.current || !roomRef.current.localParticipant) return;

    try {
      const nextState = !isMicEnabled;
      await roomRef.current.localParticipant.setMicrophoneEnabled(nextState);
      setIsMicEnabled(nextState);

      if (nextState) {
        const micPub = roomRef.current.localParticipant.getTrackPublication(Track.Source.Microphone);
        if (micPub && micPub.track && (micPub.track as any).mediaStreamTrack) {
          setMediaStreamTrack((micPub.track as any).mediaStreamTrack);
        }
      } else {
        setMediaStreamTrack(null);
      }

      addEvent(
        nextState ? "MIC_UNMUTED" : "MIC_MUTED",
        nextState ? "You unmuted microphone" : "You muted microphone",
        "info"
      );
      syncParticipants(roomRef.current);
    } catch (err: any) {
      console.error("Failed to toggle microphone:", err);
      addEvent("MIC_ERROR", "Could not toggle microphone", "error");
    }
  }, [isMicEnabled, addEvent, syncParticipants]);

  // Send Text Message through LiveKit DataChannel
  const sendChatMessage = useCallback(
    async (text: string) => {
      if (!roomRef.current || !roomRef.current.localParticipant || !text.trim()) {
        return;
      }

      const localP = roomRef.current.localParticipant;
      const cleanText = text.trim();
      const messagePayload = {
        type: "chat.message",
        message_id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        sender_id: localP.identity,
        sender_name: localP.name || displayName,
        text: cleanText,
        timestamp: new Date().toISOString(),
        version: 1,
      };

      try {
        const encoded = new TextEncoder().encode(JSON.stringify(messagePayload));
        await localP.publishData(encoded, { reliable: true });

        // Optimistically add to local messages
        const localChatMsg: LiveKitChatMessage = {
          id: messagePayload.message_id,
          senderId: messagePayload.sender_id,
          senderName: messagePayload.sender_name,
          text: cleanText,
          timestamp: messagePayload.timestamp,
          isLocal: true,
        };

        setChatMessages((prev) => [...prev, localChatMsg]);
        addEvent("CHAT_SENT", `You: ${cleanText.slice(0, 32)}`, "info");

        // Unify with Voice Transcripts view as a finalized transcript turn
        const textTurnId = `turn-txt-${Date.now()}`;
        const newTextTurn: TranscriptTurn = {
          id: textTurnId,
          speakerId: localP.identity,
          speakerName: localP.name || displayName,
          text: cleanText,
          isFinal: true,
          timestamp: new Date().toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" }),
          isLocal: true,
        };
        setTranscripts((prev) => [...prev, newTextTurn]);

        // If authenticated session token is available, orchestrate via unified backend API
        if (sttToken) {
          try {
            const apiBase = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";
            const resp = await fetch(`${apiBase}/api/v1/orchestration/text-chat`, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${sttToken}`,
              },
              body: JSON.stringify({
                room_name: roomName,
                text: cleanText,
                participant_identity: localP.identity,
                display_name: localP.name || displayName,
              }),
            });

            if (resp.ok) {
              const decision = await resp.json();
              const orchMeta: OrchestrationMetadata = {
                decisionId: decision.decision_id,
                shouldRespond: decision.eligibility.should_respond,
                triggerType: decision.eligibility.trigger_type,
                selectedBot: decision.routing.selected_bot,
                routingReason: decision.routing.reason,
                turnLockAcquired: decision.turn_lock_acquired,
                lockDeferred: !decision.turn_lock_acquired && decision.eligibility.should_respond,
              };

              setTranscripts((prev) => {
                const updated = [...prev];
                const lastIdx = updated.findIndex((t) => t.id === textTurnId);
                if (lastIdx >= 0) {
                  updated[lastIdx] = { ...updated[lastIdx], id: decision.turn_id, orchestration: orchMeta };
                }
                return updated;
              });

              setActiveRouting({
                selectedBot: decision.routing.selected_bot,
                reason: decision.routing.reason,
                confidence: decision.routing.confidence,
                lockStatus: decision.turn_lock_acquired ? "ACQUIRED" : "IDLE",
                lastTurnId: decision.turn_id,
              });

              setRoomContextState((prev) => ({
                ...prev,
                turnCount: prev.turnCount + 1,
                activeSpeakerId: localP.identity,
              }));
            }
          } catch (apiErr) {
            console.warn("Text chat orchestration call failed:", apiErr);
          }
        }
      } catch (err: any) {
        console.error("Failed to send LiveKit data message:", err);
        addEvent("CHAT_ERROR", "Failed to send message over LiveKit data channel", "error");
      }
    },
    [displayName, addEvent, sttToken, roomName]
  );

  // Hook in Real-Time STT Audio Streaming
  const { sttState, latestLatencyMs } = useLiveKitAudioStreamer({
    mediaStreamTrack,
    sttToken,
    isMicEnabled,
    onTranscript: handleTranscript,
    addEvent,
  });

  // Clean up on component unmount — bump session so in-flight connect cannot reattach
  useEffect(() => {
    return () => {
      const unmountSession = beginSession(sessionIdRef.current);
      sessionIdRef.current = unmountSession;
      const room = roomRef.current;
      roomRef.current = null;
      logLiveKitLifecycle({ event: "unmount_cleanup", sessionId: unmountSession });
      if (room) {
        void room.disconnect().finally(() => {
          try {
            room.removeAllListeners();
          } catch {
            /* ignore */
          }
        });
      }
    };
  }, []);

  return {
    connectionState,
    roomName,
    displayName,
    localIdentity,
    participants,
    isMicEnabled,
    activeSpeakerId,
    chatMessages,
    eventLog,
    errorMessage,
    sttState,
    transcripts,
    activeRouting,
    roomContextState,
    llmStatus,
    activeStreamingPreview,
    activeGeneratingBot,
    ttsStatus,
    ttsStateByBot,
    audioPlaybackBlocked,
    latestSTTLatencyMs: latestLatencyMs,
    connect,
    disconnect,
    toggleMicrophone,
    sendChatMessage,
    unlockAudio,
  };

}
