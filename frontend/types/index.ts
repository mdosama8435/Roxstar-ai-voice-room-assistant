export type ParticipantRole = "HUMAN" | "AI_AGENT";

export type MediaState =
  | "IDLE"
  | "LISTENING"
  | "SPEAKING"
  | "MUTED"
  | "THINKING"
  | "CONNECTING"
  | "DISCONNECTED";

export type RoomConnectionState =
  | "IDLE"
  | "CONNECTING"
  | "CONNECTED"
  | "RECONNECTING"
  | "DISCONNECTED"
  | "ERROR";

export interface ParticipantUI {
  id: string;
  name: string;
  role: ParticipantRole;
  personaId?: "dost" | "sathi";
  gender?: "male" | "female";
  avatarBg: string;
  badgeText: string;
  mediaState: MediaState;
  isMuted: boolean;
  isSpeaking: boolean;
  isLocal: boolean;
  isStaticPlaceholder: boolean;
}

export type TabType = "conversation" | "chat" | "events" | "analytics";

export interface PipelineStageInfo {
  id: string;
  name: string;
  status: "Not connected" | "Active" | "Phase 3" | "Future" | "Idle" | "Error";
}

export interface LiveKitChatMessage {
  id: string;
  senderId: string;
  senderName: string;
  text: string;
  timestamp: string;
  isLocal: boolean;
  botType?: BotType;
}

export interface RoomEventLogEntry {
  id: string;
  timestamp: string;
  type: string;
  message: string;
  level?: "info" | "warning" | "success" | "error";
}

export type STTState =
  | "IDLE"
  | "CONNECTING"
  | "ACTIVE"
  | "RECONNECTING"
  | "ERROR"
  | "DISABLED";

export type BotType = "DOST" | "SATHI" | "NONE";

export interface OrchestrationMetadata {
  decisionId: string;
  shouldRespond: boolean;
  triggerType: string;
  selectedBot: BotType;
  routingReason: string;
  turnLockAcquired: boolean;
  lockDeferred: boolean;
  metrics?: {
    stt_to_turn_ms?: number;
    turn_to_eligibility_ms?: number;
    eligibility_to_routing_ms?: number;
    routing_to_lock_ms?: number;
  };
}

export interface RoomContextUI {
  currentTopic: string | null;
  activeSpeakerId: string | null;
  turnCount: number;
  facts: Record<string, string[]>;
}

export interface BotRoutingUI {
  selectedBot: BotType;
  reason: string;
  confidence: number;
  lockStatus: "ACQUIRED" | "BLOCKED" | "IDLE";
  lastTurnId?: string;
}

export type LLMStatus =
  | "IDLE"
  | "STANDBY"
  | "REQUESTING"
  | "STREAMING"
  | "GENERATING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export interface AIStreamingPreview {
  requestId: string;
  bot: BotType;
  botDisplayName: string;
  text: string;
  isFinal: boolean;
}

export interface TranscriptTurn {
  id: string;
  speakerId: string;
  speakerName: string;
  text: string;
  isFinal: boolean;
  detectedLanguage?: string;
  languageConfidence?: number;
  latencyMs?: number;
  timestamp: string;
  isLocal: boolean;
  orchestration?: OrchestrationMetadata;
}

export interface LiveKitTranscriptEvent {
  type?: string;
  event_id: string;
  room_name?: string;
  room_id?: string;
  participant_identity: string;
  participant_display_name: string;
  transcript: string;
  status: "partial" | "final";
  provider?: string;
  model?: string;
  detected_language?: string;
  language_confidence?: number;
  latency_ms?: number;
  sequence?: number;
  timestamp: string;
}

