/**
 * Classify LiveKit room participants as human vs AI using identity / kind / name.
 * Real AI identities join as ai_dost / ai_sathi (LiveKit kind=agent).
 */

export type ClassifiedParticipantRole = "HUMAN" | "AI_AGENT";
export type PersonaId = "dost" | "sathi";

export interface ParticipantClassification {
  role: ClassifiedParticipantRole;
  personaId?: PersonaId;
  displayName: string;
  badgeText: string;
  gender?: "male" | "female";
  avatarBg: string;
}

const AI_IDENTITY_MAP: Record<string, PersonaId> = {
  ai_dost: "dost",
  ai_sathi: "sathi",
  agent_dost: "dost",
  agent_sathi: "sathi",
  dost: "dost",
  sathi: "sathi",
};

function personaFromName(name: string): PersonaId | undefined {
  const n = name.toLowerCase();
  if (/\bdost\b/.test(n)) return "dost";
  if (/\bsathi\b/.test(n) || /\bsaathi\b/.test(n)) return "sathi";
  return undefined;
}

/**
 * Resolve whether a LiveKit participant is an AI companion.
 * Prefer opaque identity; fall back to agent kind + display name.
 */
export function classifyLiveKitParticipant(input: {
  identity: string;
  name?: string | null;
  kind?: string | number | null;
  isLocal?: boolean;
}): ParticipantClassification {
  const identity = (input.identity || "").trim().toLowerCase();
  const name = (input.name || "").trim();
  const kindStr = String(input.kind ?? "").toLowerCase();

  let personaId: PersonaId | undefined = AI_IDENTITY_MAP[identity];
  if (!personaId && (kindStr === "agent" || kindStr === "1")) {
    personaId = personaFromName(name);
  }
  if (!personaId) {
    personaId = personaFromName(name);
  }

  if (personaId === "dost") {
    return {
      role: "AI_AGENT",
      personaId: "dost",
      displayName: name || "Roxstar AI Dost",
      badgeText: "AI Dost",
      gender: "male",
      avatarBg: "bg-gradient-to-tr from-purple-600 to-indigo-700 text-white",
    };
  }
  if (personaId === "sathi") {
    return {
      role: "AI_AGENT",
      personaId: "sathi",
      displayName: name || "Roxstar AI Sathi",
      badgeText: "AI Sathi",
      gender: "female",
      avatarBg: "bg-gradient-to-tr from-pink-600 to-rose-600 text-white",
    };
  }

  const isRahul = name.toLowerCase().includes("rahul");
  return {
    role: "HUMAN",
    displayName: name || (input.isLocal ? "You" : "Human Participant"),
    badgeText: input.isLocal ? "You (Human)" : "Human Participant",
    avatarBg: isRahul
      ? "bg-gradient-to-tr from-blue-600 to-cyan-600 text-white"
      : "bg-gradient-to-tr from-indigo-600 to-purple-600 text-white",
  };
}

/**
 * Build the participant grid list without duplicating AI slots.
 * Real LiveKit AI participants replace matching static placeholders.
 */
export function buildParticipantGridEntries<T extends { id: string; role: string; personaId?: string }>(
  liveParticipants: T[],
  placeholders: T[]
): { humans: T[]; ai: T[]; humanCount: number; aiCount: number } {
  const humans = liveParticipants.filter((p) => p.role !== "AI_AGENT");
  const liveAi = liveParticipants.filter((p) => p.role === "AI_AGENT");

  const hasPersona = (id: string) =>
    liveAi.some(
      (p) =>
        p.personaId === id ||
        p.id.toLowerCase().includes(id) ||
        p.id.toLowerCase() === `ai_${id}`
    );

  const standby = placeholders.filter((ph) => {
    const pid = (ph.personaId || "").toLowerCase();
    if (!pid) return true;
    return !hasPersona(pid);
  });

  const ai = [...liveAi, ...standby];
  return {
    humans,
    ai,
    humanCount: humans.length,
    aiCount: Math.max(liveAi.length, placeholders.length > 0 ? 2 : liveAi.length),
  };
}
