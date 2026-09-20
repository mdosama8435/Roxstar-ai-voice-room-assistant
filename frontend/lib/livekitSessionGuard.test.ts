import { describe, expect, it, vi } from "vitest";
import {
  beginSession,
  isActiveRoomInstance,
  isCurrentSession,
  scheduleDeferredConnect,
  shouldApplyRoomEvent,
} from "./livekitSessionGuard";

describe("livekitSessionGuard (Phase 3F.9.1)", () => {
  it("beginSession increments monotonically", () => {
    expect(beginSession(0)).toBe(1);
    expect(beginSession(7)).toBe(8);
  });

  it("isCurrentSession distinguishes active vs stale connect epochs", () => {
    expect(isCurrentSession(3, 3)).toBe(true);
    expect(isCurrentSession(4, 3)).toBe(false);
  });

  it("isActiveRoomInstance requires exact Room identity", () => {
    const a = { id: "a" };
    const b = { id: "b" };
    expect(isActiveRoomInstance(a, a)).toBe(true);
    expect(isActiveRoomInstance(a, b)).toBe(false);
    expect(isActiveRoomInstance(null, a)).toBe(false);
  });

  it("shouldApplyRoomEvent rejects stale session even if room ref matches", () => {
    const room = { id: "r1" };
    expect(
      shouldApplyRoomEvent({
        activeSessionId: 2,
        eventSessionId: 1,
        activeRoom: room,
        eventRoom: room,
      })
    ).toBe(false);
  });

  it("shouldApplyRoomEvent rejects detached/stale Room after leave/rejoin", () => {
    const oldRoom = { id: "old" };
    const newRoom = { id: "new" };
    expect(
      shouldApplyRoomEvent({
        activeSessionId: 2,
        eventSessionId: 2,
        activeRoom: newRoom,
        eventRoom: oldRoom,
      })
    ).toBe(false);
  });

  it("shouldApplyRoomEvent allows only the live session+room pair", () => {
    const room = { id: "live" };
    expect(
      shouldApplyRoomEvent({
        activeSessionId: 5,
        eventSessionId: 5,
        activeRoom: room,
        eventRoom: room,
      })
    ).toBe(true);
  });

  it("intentional leave pattern: clearing active room blocks Disconnected handlers", () => {
    const room = { id: "leaving" };
    // Hook clears roomRef before disconnect; Disconnected must not apply.
    expect(
      shouldApplyRoomEvent({
        activeSessionId: 9,
        eventSessionId: 8,
        activeRoom: null,
        eventRoom: room,
      })
    ).toBe(false);
  });

  it("scheduleDeferredConnect cancels when cleanup runs (StrictMode-safe)", () => {
    vi.useFakeTimers();
    const run = vi.fn();
    const cancel = scheduleDeferredConnect(run);
    cancel();
    vi.runAllTimers();
    expect(run).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("scheduleDeferredConnect runs once after settle", () => {
    vi.useFakeTimers();
    const run = vi.fn();
    scheduleDeferredConnect(run);
    expect(run).not.toHaveBeenCalled();
    vi.runAllTimers();
    expect(run).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("StrictMode double-mount simulation: first schedule cancelled, second runs once", () => {
    vi.useFakeTimers();
    const connect = vi.fn();
    // Mount A
    const cleanupA = scheduleDeferredConnect(() => connect("A"));
    // Unmount A (StrictMode)
    cleanupA();
    // Mount B
    scheduleDeferredConnect(() => connect("B"));
    vi.runAllTimers();
    expect(connect).toHaveBeenCalledTimes(1);
    expect(connect).toHaveBeenCalledWith("B");
    vi.useRealTimers();
  });
});
