"use client";

import React, { useState } from "react";
import { MicOff, Mic, LogOut, LogIn, Send, User, RefreshCw, AlertCircle, Radio } from "lucide-react";
import { useLiveKit } from "@/hooks/LiveKitContext";

export const RoomControls: React.FC = () => {
  const {
    connectionState,
    roomName: activeRoomName,
    displayName: activeDisplayName,
    isMicEnabled,
    errorMessage,
    audioPlaybackBlocked,
    connect,
    disconnect,
    toggleMicrophone,
    sendChatMessage,
    unlockAudio,
  } = useLiveKit();

  const [inputRoom, setInputRoom] = useState<string>("roxstar-test");
  const [inputName, setInputName] = useState<string>("Rahul");
  const [quickMsg, setQuickMsg] = useState<string>("");
  const [showJoinModal, setShowJoinModal] = useState<boolean>(false);

  const isConnected = connectionState === "CONNECTED";
  const isConnecting = connectionState === "CONNECTING";

  const handleJoin = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputRoom.trim() || !inputName.trim()) return;
    await connect({
      roomName: inputRoom.trim(),
      displayName: inputName.trim(),
    });
    setShowJoinModal(false);
  };

  const handleSendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    if (!quickMsg.trim() || !isConnected) return;
    sendChatMessage(quickMsg);
    setQuickMsg("");
  };

  return (
    <>
      <div className="h-20 w-full glass-panel border-t border-slate-800 px-6 flex items-center justify-between gap-4 flex-shrink-0 z-20">
        <div className="flex items-center gap-2.5">
          {!isConnected ? (
            <div className="flex items-center gap-2">
              <button
                id="btn-open-join-modal"
                onClick={() => setShowJoinModal(true)}
                disabled={isConnecting}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-glow-purple transition-all"
              >
                {isConnecting ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Connecting...</span>
                  </>
                ) : (
                  <>
                    <LogIn className="w-4 h-4" />
                    <span>Join Room</span>
                  </>
                )}
              </button>

              <div className="hidden sm:flex items-center gap-1.5 pl-2 border-l border-slate-800">
                <span className="text-[11px] text-slate-500 mr-1">Join as:</span>
                <button
                  id="btn-quick-join-rahul"
                  onClick={() => {
                    setInputName("Rahul");
                    connect({ roomName: inputRoom, displayName: "Rahul" });
                  }}
                  disabled={isConnecting}
                  className="px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-medium text-slate-300 transition-colors"
                >
                  Rahul
                </button>
                <button
                  id="btn-quick-join-priya"
                  onClick={() => {
                    setInputName("Priya");
                    connect({ roomName: inputRoom, displayName: "Priya" });
                  }}
                  disabled={isConnecting}
                  className="px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-medium text-slate-300 transition-colors"
                >
                  Priya
                </button>
              </div>
            </div>
          ) : (
            <>
              <button
                id="btn-toggle-mic"
                type="button"
                onClick={toggleMicrophone}
                aria-label={isMicEnabled ? "Mute microphone" : "Unmute microphone"}
                aria-pressed={isMicEnabled}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500/60 ${
                  isMicEnabled
                    ? "bg-slate-900 border border-slate-700 text-slate-200 hover:border-purple-500/50"
                    : "bg-rose-950/40 border border-rose-800/50 text-rose-300 hover:bg-rose-950/60"
                }`}
                title={isMicEnabled ? "Mute Microphone" : "Unmute Microphone"}
              >
                {isMicEnabled ? <Mic className="w-4 h-4" aria-hidden /> : <MicOff className="w-4 h-4" aria-hidden />}
                <span className="hidden sm:inline">
                  {isMicEnabled ? "Mic on" : "Mic off"}
                </span>
              </button>

              <button
                id="btn-start-speaking"
                onClick={() => {
                  if (!isMicEnabled) void toggleMicrophone();
                }}
                className="flex items-center gap-2 px-5 py-2.5 rounded-2xl bg-gradient-to-r from-pink-600 to-purple-600 hover:from-pink-500 hover:to-purple-500 text-white text-xs font-bold shadow-lg shadow-pink-500/30 transition-all"
                title="Enable mic / start speaking"
              >
                <Radio className="w-4 h-4" />
                <span>{isMicEnabled ? "You're Live" : "Start Speaking"}</span>
              </button>

              {audioPlaybackBlocked && (
                <button
                  id="btn-enable-audio"
                  type="button"
                  onClick={() => void unlockAudio()}
                  className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-amber-950/50 border border-amber-700/60 text-amber-200 hover:bg-amber-950/70 text-xs font-semibold transition-all animate-pulse"
                  title="Browser blocked autoplay — click to hear AI and other participants"
                >
                  <Radio className="w-4 h-4" />
                  <span>Enable Audio</span>
                </button>
              )}

              <button
                id="btn-disconnect-room"
                type="button"
                onClick={disconnect}
                aria-label="Leave room"
                className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-rose-950/40 border border-rose-800/50 text-rose-300 hover:bg-rose-950/60 text-xs font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500/50"
                title="Disconnect from Room"
              >
                <LogOut className="w-4 h-4" />
                <span>Leave</span>
              </button>

              <div className="hidden lg:flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900/60 border border-slate-800/60 text-xs text-slate-400">
                <User className="w-3.5 h-3.5 text-purple-400" />
                <span>
                  Logged in as: <strong className="text-white">{activeDisplayName}</strong>
                </span>
              </div>

              <span className="hidden xl:inline text-[11px] text-slate-500">Press Space to talk</span>
            </>
          )}
        </div>

        {errorMessage && (
          <div
            id="banner-error-message"
            className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-xl bg-rose-950/50 border border-rose-800/60 text-xs text-rose-300 animate-fadeIn"
          >
            <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
            <span className="truncate max-w-xs">{errorMessage}</span>
          </div>
        )}

        <form onSubmit={handleSendMessage} className="flex-1 max-w-lg flex items-center gap-2">
          <input
            id="input-chat-message"
            type="text"
            value={quickMsg}
            onChange={(e) => setQuickMsg(e.target.value)}
            disabled={!isConnected}
            placeholder={
              isConnected ? "Send instant message to room..." : "Join room to send messages"
            }
            className={`flex-1 bg-slate-900/90 border rounded-xl px-4 py-2 text-xs focus:outline-none transition-colors ${
              isConnected
                ? "border-slate-800 text-slate-200 focus:border-purple-500"
                : "border-slate-800/60 text-slate-600 cursor-not-allowed"
            }`}
          />

          <button
            id="btn-send-chat-message"
            type="submit"
            disabled={!isConnected || !quickMsg.trim()}
            className={`p-2 rounded-xl transition-all ${
              isConnected && quickMsg.trim()
                ? "bg-purple-600 text-white hover:bg-purple-500 shadow-glow-purple"
                : "bg-slate-800 text-slate-600 cursor-not-allowed opacity-50"
            }`}
            title="Send chat message"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>

      {showJoinModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="glass-card rounded-2xl p-6 w-full max-w-md border border-purple-500/30 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <LogIn className="w-5 h-5 text-purple-400" />
                Join LiveKit Room
              </h3>
              <button
                id="btn-close-modal"
                onClick={() => setShowJoinModal(false)}
                className="text-slate-400 hover:text-white text-xs p-1"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleJoin} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Room Name</label>
                <input
                  id="input-modal-room-name"
                  type="text"
                  value={inputRoom}
                  onChange={(e) => setInputRoom(e.target.value)}
                  placeholder="e.g. roxstar-test"
                  required
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-purple-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Display Name</label>
                <input
                  id="input-modal-display-name"
                  type="text"
                  value={inputName}
                  onChange={(e) => setInputName(e.target.value)}
                  placeholder="e.g. Rahul or Priya"
                  required
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-purple-500"
                />
              </div>

              <div className="space-y-1">
                <span className="text-[11px] text-slate-500">Quick demo presets:</span>
                <div className="flex gap-2">
                  <button
                    id="btn-modal-preset-rahul"
                    type="button"
                    onClick={() => setInputName("Rahul")}
                    className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-medium border transition-colors ${
                      inputName === "Rahul"
                        ? "bg-purple-600/30 border-purple-500 text-purple-300"
                        : "bg-slate-900 border-slate-800 text-slate-400 hover:text-white"
                    }`}
                  >
                    Rahul (Browser 1)
                  </button>
                  <button
                    id="btn-modal-preset-priya"
                    type="button"
                    onClick={() => setInputName("Priya")}
                    className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-medium border transition-colors ${
                      inputName === "Priya"
                        ? "bg-pink-600/30 border-pink-500 text-pink-300"
                        : "bg-slate-900 border-slate-800 text-slate-400 hover:text-white"
                    }`}
                  >
                    Priya (Browser 2)
                  </button>
                </div>
              </div>

              <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-800">
                <button
                  id="btn-modal-cancel"
                  type="button"
                  onClick={() => setShowJoinModal(false)}
                  className="px-4 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  id="btn-modal-submit-join"
                  type="submit"
                  disabled={isConnecting}
                  className="px-5 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-glow-purple flex items-center gap-2"
                >
                  {isConnecting && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  <span>Join Room as {inputName}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
};
