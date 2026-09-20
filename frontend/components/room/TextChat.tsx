"use client";

import React, { useState, useRef, useEffect } from "react";
import { Send, MessageSquare, User, Lock, Bot, Sparkles } from "lucide-react";
import { useLiveKit } from "@/hooks/LiveKitContext";

export const TextChat: React.FC = () => {
  const { chatMessages, sendChatMessage, connectionState, activeStreamingPreview } = useLiveKit();
  const [inputText, setInputText] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const isConnected = connectionState === "CONNECTED";

  // Auto-scroll to bottom of chat on new messages or streaming chunk updates
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages, activeStreamingPreview]);

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || !isConnected) return;
    sendChatMessage(inputText);
    setInputText("");
  };

  return (
    <div className="h-full flex flex-col justify-between">
      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto space-y-3 pr-2 max-h-[360px]">
        {chatMessages.length === 0 && !activeStreamingPreview ? (
          <div className="h-full flex flex-col items-center justify-center p-8 text-center space-y-3">
            <div className="w-10 h-10 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-500">
              <MessageSquare className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs font-semibold text-slate-300">
                LiveKit DataChannel Chat
              </p>
              <p className="text-[11px] text-slate-500 max-w-sm mt-1">
                {isConnected
                  ? "No text messages yet. Send a message to participants in this room."
                  : "Connect to the LiveKit room to chat in real time with participants."}
              </p>
            </div>
          </div>
        ) : (
          <>
            {chatMessages.map((msg) => {
              const isAi = Boolean(msg.botType) || msg.senderId.startsWith("ai_");
              const isDost = msg.botType === "DOST" || msg.senderName.includes("Dost");

              return (
                <div
                  key={msg.id}
                  className={`flex flex-col ${msg.isLocal ? "items-end" : "items-start"}`}
                >
                  <div className="flex items-center gap-1.5 mb-0.5 text-[11px] text-slate-400">
                    {isAi ? (
                      isDost ? (
                        <Bot className="w-3.5 h-3.5 text-blue-400" />
                      ) : (
                        <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                      )
                    ) : (
                      <User className="w-3 h-3 text-slate-500" />
                    )}
                    <span
                      className={`font-medium ${
                        isAi
                          ? isDost
                            ? "text-blue-300 font-semibold"
                            : "text-purple-300 font-semibold"
                          : "text-slate-300"
                      }`}
                    >
                      {msg.senderName} {msg.isLocal && "(You)"}
                    </span>
                    <span className="text-[10px] text-slate-500">
                      {new Date(msg.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </div>
                  <div
                    className={`px-3 py-2 rounded-xl text-xs max-w-md break-words ${
                      isAi
                        ? isDost
                          ? "bg-blue-950/40 border border-blue-800/60 text-blue-100 rounded-tl-sm shadow-sm"
                          : "bg-purple-950/40 border border-purple-800/60 text-purple-100 rounded-tl-sm shadow-sm"
                        : msg.isLocal
                        ? "bg-purple-600/30 border border-purple-500/40 text-purple-100 rounded-tr-sm"
                        : "bg-slate-800/80 border border-slate-700/60 text-slate-200 rounded-tl-sm"
                    }`}
                  >
                    {msg.text}
                  </div>
                </div>
              );
            })}

            {/* Ephemeral Streaming Preview (Does NOT create permanent message per chunk) */}
            {activeStreamingPreview && (
              <div className="flex flex-col items-start animate-fade-in">
                <div className="flex items-center gap-1.5 mb-0.5 text-[11px]">
                  <Bot className="w-3.5 h-3.5 text-purple-400 animate-spin" />
                  <span className="font-semibold text-purple-300 font-mono">
                    {activeStreamingPreview.botDisplayName} (Generating...)
                  </span>
                </div>
                <div className="px-3 py-2 rounded-xl text-xs max-w-md break-words bg-purple-950/40 border border-purple-800/60 text-purple-200 rounded-tl-sm italic">
                  {activeStreamingPreview.text || "Thinking..."}
                  <span className="inline-block w-1.5 h-3 ml-1 bg-purple-400 animate-pulse" />
                </div>
              </div>
            )}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Message Input Form */}
      <form onSubmit={handleSend} className="mt-4 pt-3 border-t border-slate-800/80 flex items-center gap-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            disabled={!isConnected}
            placeholder={
              isConnected
                ? "Type a message to the room via LiveKit DataChannel..."
                : "Connect to the LiveKit room to type messages"
            }
            className={`w-full bg-slate-950/80 border rounded-xl px-4 py-2 text-xs focus:outline-none transition-colors pr-8 ${
              isConnected
                ? "border-slate-800 text-slate-200 focus:border-purple-500"
                : "border-slate-800/50 text-slate-600 cursor-not-allowed"
            }`}
          />
          {!isConnected && (
            <Lock className="w-3.5 h-3.5 text-slate-600 absolute right-3 top-1/2 -translate-y-1/2" />
          )}
        </div>

        <button
          type="submit"
          disabled={!isConnected || !inputText.trim()}
          className={`p-2 rounded-xl transition-all ${
            isConnected && inputText.trim()
              ? "bg-purple-600 text-white hover:bg-purple-500 shadow-glow-purple"
              : "bg-slate-800 text-slate-600 cursor-not-allowed opacity-50"
          }`}
          title="Send message"
        >
          <Send className="w-4 h-4" />
        </button>
      </form>
    </div>
  );
};
