"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Mic,
  PlusCircle,
  LogIn,
  History,
  BarChart2,
  BookOpen,
  Sparkles,
  FlaskConical,
  Settings as SettingsIcon,
  Radio,
  AudioWaveform,
  Music2,
} from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/room/demo", label: "Voice Room", icon: Mic, live: true },
  { href: "/create-room", label: "Create Room", icon: PlusCircle },
  { href: "/join-room", label: "Join Room", icon: LogIn },
  { href: "/chat-history", label: "Chat History", icon: History },
  { href: "/analytics", label: "Analytics", icon: BarChart2 },
  { href: "/documentation", label: "Documentation", icon: BookOpen },
] as const;

const TOOL_ITEMS = [
  { href: "/tools/summary", label: "Conversation Summary", icon: Sparkles },
  { href: "/tools/scenarios", label: "Test Scenarios", icon: FlaskConical },
  { href: "/settings", label: "Settings", icon: SettingsIcon },
] as const;

function navActive(pathname: string, href: string): boolean {
  if (href === "/room/demo") {
    return pathname.startsWith("/room");
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

const linkFocus =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500/60 focus-visible:ring-offset-2 focus-visible:ring-offset-background";

export const Sidebar: React.FC = () => {
  const pathname = usePathname() || "/";

  return (
    <aside
      className="w-14 md:w-64 h-full flex-shrink-0 glass-panel border-r border-slate-800/80 flex flex-col justify-between p-2 md:p-4 z-20 overflow-y-auto"
      aria-label="Main navigation"
    >
      <div className="space-y-4 md:space-y-6">
        <div className="px-1 md:px-2 py-2 md:py-3">
          <div className="flex items-center gap-3 justify-center md:justify-start">
            <div className="w-9 h-9 md:w-10 md:h-10 rounded-xl bg-gradient-to-tr from-purple-600 via-violet-500 to-pink-500 flex items-center justify-center shadow-glow-purple flex-shrink-0">
              <AudioWaveform className="w-5 h-5 md:w-6 md:h-6 text-white" aria-hidden />
            </div>
            <div className="hidden md:block min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-lg tracking-tight text-white">
                  Rox<span className="text-pink-400">Star</span>
                </span>
                <span className="text-[10px] uppercase tracking-widest text-purple-400 font-semibold px-1 py-0.5 bg-purple-950/60 rounded border border-purple-800/30">
                  AI
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-medium italic">
                &ldquo;Let it be heard.&rdquo;
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-1">
          <p className="hidden md:block px-3 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
            Navigation
          </p>

          {NAV_ITEMS.map((item) => {
            const active = navActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                title={item.label}
                aria-label={item.label}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center justify-center md:justify-between px-2 md:px-3 py-2.5 rounded-lg text-sm font-medium transition-all",
                  linkFocus,
                  active
                    ? "bg-purple-600/15 text-purple-300 border border-purple-500/30 shadow-sm"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40 border border-transparent"
                )}
              >
                <div className="flex items-center gap-2.5">
                  <item.icon
                    className={cn("w-4 h-4 flex-shrink-0", active ? "text-purple-400" : "text-slate-500")}
                    aria-hidden
                  />
                  <span className="hidden md:inline">{item.label}</span>
                </div>
                {"live" in item && item.live && active && (
                  <span
                    className="hidden md:block w-2 h-2 rounded-full bg-emerald-400 animate-pulse"
                    aria-hidden
                  />
                )}
              </Link>
            );
          })}
        </div>

        <div className="space-y-1 pt-1 md:pt-2">
          <p className="hidden md:block px-3 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
            Tools
          </p>

          {TOOL_ITEMS.map((item) => {
            const active = navActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                title={item.label}
                aria-label={item.label}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center justify-center md:justify-start gap-2.5 px-2 md:px-3 py-2.5 rounded-lg text-sm font-medium transition-all",
                  linkFocus,
                  active
                    ? "bg-purple-600/15 text-purple-300 border border-purple-500/30"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40 border border-transparent"
                )}
              >
                <item.icon
                  className={cn(
                    "w-4 h-4 flex-shrink-0",
                    item.href.includes("summary")
                      ? "text-amber-400"
                      : item.href.includes("scenarios")
                        ? "text-cyan-400"
                        : "text-slate-500"
                  )}
                  aria-hidden
                />
                <span className="hidden md:inline">{item.label}</span>
              </Link>
            );
          })}
        </div>
      </div>

      <div className="hidden md:block space-y-3">
        <div className="p-3 rounded-xl bg-gradient-to-br from-purple-950/80 to-slate-900/80 border border-purple-800/40 space-y-2">
          <div className="flex items-center gap-2">
            <Music2 className="w-4 h-4 text-pink-400" aria-hidden />
            <span className="text-xs font-semibold text-slate-200">
              AI for a More Musical World
            </span>
          </div>
          <p className="text-[11px] text-slate-400 leading-snug">
            Dual-bot voice rooms with real STT, LLM, and TTS.
          </p>
        </div>

        <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400 flex items-center gap-1.5">
              <Radio className="w-3.5 h-3.5 text-purple-400" aria-hidden />
              Live stack
            </span>
            <Badge variant="purple" size="sm">
              Phase 3F
            </Badge>
          </div>
          <p className="text-[11px] text-slate-400 leading-snug">
            Voice room · Gemini · Sarvam STT/TTS · LiveKit
          </p>
        </div>
      </div>
    </aside>
  );
};
