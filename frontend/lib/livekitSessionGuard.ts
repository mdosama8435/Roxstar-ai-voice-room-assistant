/**
 * Phase 3F.9.1 — LiveKit room session lifecycle guards.
 * Pure helpers so connect/disconnect races and stale Room events
 * cannot mutate UI after a newer session owns the hook.
 */

export type LiveKitLifecycleEvent =
  | "session_begin"
  | "session_superseded"
  | "room_created"
  | "room_connect_start"
  | "room_connected"
  | "room_reconnect"
  | "room_reconnected"
  | "intentional_leave"
  | "stale_event_ignored"
  | "teardown"
  | "unmount_cleanup";

export interface LiveKitLifecycleLog {
  event: LiveKitLifecycleEvent;
  sessionId: number;
  roomInstanceId?: number;
  detail?: string;
}

/** Monotonic session ids for connect/leave epochs. */
export function beginSession(currentSessionId: number): number {
  return currentSessionId + 1;
}

/** True when an async connect/event still belongs to the active session. */
export function isCurrentSession(activeSessionId: number, eventSessionId: number): boolean {
  return activeSessionId === eventSessionId;
}

/**
 * True only when the Room that emitted the event is still the hook's active Room.
 * Prevents detached/stale instances from calling setState after leave/rejoin.
 */
export function isActiveRoomInstance<T>(activeRoom: T | null, eventRoom: T): boolean {
  return activeRoom !== null && activeRoom === eventRoom;
}

/**
 * Combined gate used by RoomEvent handlers.
 * Intentional leave bumps the session and clears the active room before disconnect,
 * so stale Disconnected/Reconnecting must not flip UI away from IDLE/CONNECTING.
 */
export function shouldApplyRoomEvent<T>(opts: {
  activeSessionId: number;
  eventSessionId: number;
  activeRoom: T | null;
  eventRoom: T;
}): boolean {
  return (
    isCurrentSession(opts.activeSessionId, opts.eventSessionId) &&
    isActiveRoomInstance(opts.activeRoom, opts.eventRoom)
  );
}

/**
 * Dev-only structured lifecycle logger. Never accepts tokens/secrets.
 */
export function logLiveKitLifecycle(entry: LiveKitLifecycleLog): void {
  if (process.env.NODE_ENV === "production") return;
  const { event, sessionId, roomInstanceId, detail } = entry;
  // eslint-disable-next-line no-console
  console.info("[lk-lifecycle]", {
    event,
    sessionId,
    ...(roomInstanceId !== undefined ? { roomInstanceId } : {}),
    ...(detail ? { detail } : {}),
  });
}

/**
 * Schedules a one-shot connect after the current StrictMode mount cycle settles.
 * Clearing the timer on cleanup prevents the aborted first WebSocket handshake
 * that produces LiveKit "signal stream" / "websocket error during connection" logs.
 */
export function scheduleDeferredConnect(
  run: () => void,
  schedule: (cb: () => void) => ReturnType<typeof setTimeout> = (cb) => setTimeout(cb, 0),
  cancel: (id: ReturnType<typeof setTimeout>) => void = clearTimeout
): () => void {
  const id = schedule(run);
  return () => cancel(id);
}
