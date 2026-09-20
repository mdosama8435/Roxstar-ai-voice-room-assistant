"use client";

import React, { useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { RoomShell } from "@/components/room/RoomShell";
import { LiveKitProvider, useLiveKit } from "@/hooks/LiveKitContext";
import { scheduleDeferredConnect } from "@/lib/livekitSessionGuard";

/** Connects when ?room=&name=&auto=1 is present (from Create/Join/Scenarios). */
function AutoJoinFromQuery() {
  const params = useSearchParams();
  const { connect, connectionState } = useLiveKit();
  const startedKey = useRef<string | null>(null);
  const connectRef = useRef(connect);
  connectRef.current = connect;

  const auto = params.get("auto");
  const room = params.get("room");
  const name = params.get("name");

  useEffect(() => {
    if (connectionState === "CONNECTED" || connectionState === "CONNECTING") return;
    if (auto !== "1" || !room?.trim() || !name?.trim()) return;
    const key = `${room.trim()}::${name.trim()}`;
    if (startedKey.current === key) return;

    // Defer past React StrictMode's mount→unmount→remount so we do not open a
    // LiveKit signal WebSocket that is immediately aborted (SDK console errors).
    // Depend on primitive query values (not the params object) so remount/re-render
    // does not cancel the deferred connect before it fires.
    return scheduleDeferredConnect(() => {
      if (startedKey.current === key) return;
      startedKey.current = key;
      void connectRef.current({ roomName: room.trim(), displayName: name.trim() });
    });
  }, [auto, room, name, connectionState]);

  return null;
}

function DemoRoomInner() {
  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">
      <Sidebar />
        <div className="flex-1 flex flex-col h-full overflow-hidden min-w-0">
          <Topbar />
          <AutoJoinFromQuery />
          <RoomShell />
        </div>
    </div>
  );
}

export default function DemoRoomPage() {
  return (
    <LiveKitProvider>
      <React.Suspense fallback={null}>
        <DemoRoomInner />
      </React.Suspense>
    </LiveKitProvider>
  );
}
