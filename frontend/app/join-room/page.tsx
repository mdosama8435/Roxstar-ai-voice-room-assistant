"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { LogIn, Hash, User, ArrowRight } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";

const ROOM_PATTERN = /^[a-zA-Z0-9_\-]+$/;

export default function JoinRoomPage() {
  const router = useRouter();
  const [roomName, setRoomName] = useState("roxstar-test");
  const [displayName, setDisplayName] = useState("Priya");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleJoin = (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting) return;
    const room = roomName.trim();
    const name = displayName.trim() || "Guest";

    if (!room || room.length < 2 || room.length > 128) {
      setError("Room ID must be 2–128 characters.");
      return;
    }
    if (!ROOM_PATTERN.test(room)) {
      setError("Room ID may only contain letters, numbers, hyphens, and underscores.");
      return;
    }
    if (!name || name.length > 64) {
      setError("Display name is required (max 64 characters).");
      return;
    }

    setError(null);
    setSubmitting(true);
    router.push(
      `/room/demo?room=${encodeURIComponent(room)}&name=${encodeURIComponent(name)}&auto=1`
    );
  };

  return (
    <AppShell>
      <div className="max-w-lg mx-auto p-8 space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <LogIn className="w-6 h-6 text-purple-400" />
            Join Room
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Enter an existing room ID and display name to connect via LiveKit token.
          </p>
        </div>

        <form
          onSubmit={handleJoin}
          className="glass-card rounded-2xl border border-slate-800 p-6 space-y-4"
        >
          <div>
            <label htmlFor="join-room-id" className="block text-xs font-medium text-slate-400 mb-1.5">
              Room ID
            </label>
            <div className="relative">
              <Hash className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-purple-400" aria-hidden />
              <input
                id="join-room-id"
                value={roomName}
                onChange={(e) => {
                  setRoomName(e.target.value);
                  setError(null);
                }}
                className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-3 py-2.5 text-sm text-white focus:outline-none focus:border-purple-500 focus-visible:ring-2 focus-visible:ring-purple-500/40"
                placeholder="roxstar-test"
                required
                pattern="[a-zA-Z0-9_\-]+"
                minLength={2}
                maxLength={128}
                disabled={submitting}
              />
            </div>
          </div>

          <div>
            <label htmlFor="join-display-name" className="block text-xs font-medium text-slate-400 mb-1.5">
              Display name
            </label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-cyan-400" aria-hidden />
              <input
                id="join-display-name"
                value={displayName}
                onChange={(e) => {
                  setDisplayName(e.target.value);
                  setError(null);
                }}
                className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-3 py-2.5 text-sm text-white focus:outline-none focus:border-purple-500 focus-visible:ring-2 focus-visible:ring-purple-500/40"
                placeholder="Priya"
                required
                maxLength={64}
                disabled={submitting}
              />
            </div>
          </div>

          <div className="flex gap-2">
            {["Rahul", "Priya"].map((preset) => (
              <button
                key={preset}
                type="button"
                onClick={() => setDisplayName(preset)}
                className={`flex-1 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  displayName === preset
                    ? "bg-purple-600/30 border-purple-500 text-purple-300"
                    : "bg-slate-900 border-slate-800 text-slate-400 hover:text-white"
                }`}
              >
                {preset}
              </button>
            ))}
          </div>

          {error && (
            <p role="alert" className="text-xs text-rose-400 bg-rose-950/40 border border-rose-800/50 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 disabled:opacity-60 disabled:pointer-events-none text-white text-sm font-semibold shadow-glow-purple transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400"
          >
            {submitting ? "Opening room…" : "Join Voice Room"}
            <ArrowRight className="w-4 h-4" aria-hidden />
          </button>
        </form>
      </div>
    </AppShell>
  );
}
