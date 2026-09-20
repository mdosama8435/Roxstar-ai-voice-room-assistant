/**
 * Safe settings / status helpers — never surface secrets.
 */

export const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";

export function getBackendUrl(): string {
  return process.env.NEXT_PUBLIC_BACKEND_URL || DEFAULT_BACKEND_URL;
}

/** App routes that sidebar / docs expect to remain valid. */
export const APP_NAV_ROUTES = [
  "/room/demo",
  "/create-room",
  "/join-room",
  "/chat-history",
  "/analytics",
  "/documentation",
  "/tools/summary",
  "/tools/scenarios",
  "/settings",
] as const;

const SECRET_KEY_RE =
  /(api[_-]?key|access[_-]?token|secret|password|authorization|bearer|credential|private[_-]?key)/i;

export function looksLikeSecretKey(key: string): boolean {
  return SECRET_KEY_RE.test(key);
}

export function looksLikeSecretValue(value: unknown): boolean {
  if (typeof value !== "string") return false;
  const v = value.trim();
  if (v.length < 8) return false;
  // Long opaque tokens / key-shaped strings
  if (/^(sk-|lk_|AIza|Bearer\s)/i.test(v)) return true;
  if (/^[A-Za-z0-9_\-]{32,}$/.test(v) && !/^https?:\/\//i.test(v)) return true;
  return false;
}

/**
 * Recursively drop secret-looking keys/values from a JSON-like object
 * before rendering in Settings.
 */
export function sanitizeForDisplay(input: unknown): unknown {
  if (input === null || input === undefined) return input;
  if (Array.isArray(input)) {
    return input.map((item) => sanitizeForDisplay(item));
  }
  if (typeof input === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(input as Record<string, unknown>)) {
      if (looksLikeSecretKey(k)) continue;
      if (looksLikeSecretValue(v)) continue;
      out[k] = sanitizeForDisplay(v);
    }
    return out;
  }
  if (looksLikeSecretValue(input)) return "[redacted]";
  return input;
}

export type ProviderFlags = {
  livekit_configured?: boolean;
  sarvam_configured?: boolean;
  llm_configured?: boolean;
  primary_provider?: string;
  fallback_provider?: string;
  fallback_enabled?: boolean;
  primary_configured?: boolean;
  fallback_configured?: boolean;
};

export type SafeSystemStatus = {
  status?: string;
  service?: string;
  version?: string;
  environment?: string;
  providers?: ProviderFlags;
};

export function pickSafeSystemStatus(raw: unknown): SafeSystemStatus | null {
  if (!raw || typeof raw !== "object") return null;
  const cleaned = sanitizeForDisplay(raw) as Record<string, unknown>;
  const providersRaw = cleaned.providers;
  let providers: ProviderFlags | undefined;
  if (providersRaw && typeof providersRaw === "object") {
    const p = providersRaw as Record<string, unknown>;
    providers = {
      livekit_configured: Boolean(p.livekit_configured),
      sarvam_configured: Boolean(p.sarvam_configured),
      llm_configured: Boolean(p.llm_configured),
      primary_provider: typeof p.primary_provider === "string" ? p.primary_provider : undefined,
      fallback_provider: typeof p.fallback_provider === "string" ? p.fallback_provider : undefined,
      fallback_enabled: typeof p.fallback_enabled === "boolean" ? p.fallback_enabled : undefined,
      primary_configured: typeof p.primary_configured === "boolean" ? p.primary_configured : undefined,
      fallback_configured:
        typeof p.fallback_configured === "boolean" ? p.fallback_configured : undefined,
    };
  }
  return {
    status: typeof cleaned.status === "string" ? cleaned.status : undefined,
    service: typeof cleaned.service === "string" ? cleaned.service : undefined,
    version: typeof cleaned.version === "string" ? cleaned.version : undefined,
    environment: typeof cleaned.environment === "string" ? cleaned.environment : undefined,
    providers,
  };
}

export type LocalDataStats = {
  chatConversations: number;
  chatMessages: number;
  pipelineEvents: number;
  scenarioResults: number;
};

export function readLocalDataStats(
  storage: Pick<Storage, "getItem"> | null
): LocalDataStats {
  const empty: LocalDataStats = {
    chatConversations: 0,
    chatMessages: 0,
    pipelineEvents: 0,
    scenarioResults: 0,
  };
  if (!storage) return empty;
  try {
    const chatRaw = storage.getItem("roxstar-chat-history");
    if (chatRaw) {
      const parsed = JSON.parse(chatRaw);
      const convs = Array.isArray(parsed?.conversations) ? parsed.conversations : [];
      empty.chatConversations = convs.length;
      empty.chatMessages = convs.reduce(
        (n: number, c: { messages?: unknown[] }) =>
          n + (Array.isArray(c?.messages) ? c.messages.length : 0),
        0
      );
    }
    const pipeRaw = storage.getItem("roxstar-analytics-pipeline");
    if (pipeRaw) {
      const parsed = JSON.parse(pipeRaw);
      empty.pipelineEvents = Array.isArray(parsed?.events) ? parsed.events.length : 0;
    }
    const scenRaw = storage.getItem("roxstar-scenario-results");
    if (scenRaw) {
      const parsed = JSON.parse(scenRaw);
      empty.scenarioResults =
        parsed?.byId && typeof parsed.byId === "object" ? Object.keys(parsed.byId).length : 0;
    }
  } catch {
    // ignore parse errors
  }
  return empty;
}
