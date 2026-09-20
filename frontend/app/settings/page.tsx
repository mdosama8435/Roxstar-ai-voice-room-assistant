"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Settings as SettingsIcon,
  Server,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Trash2,
  Wifi,
  Layers,
  AlertCircle,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import {
  getBackendUrl,
  pickSafeSystemStatus,
  readLocalDataStats,
  type LocalDataStats,
  type SafeSystemStatus,
} from "@/lib/settingsInfo";
import { listConversations, loadChatHistoryStore, saveChatHistoryStore } from "@/lib/chatHistory";
import { savePipelineStore } from "@/lib/analytics";
import { resetAllScenarioStates } from "@/lib/testScenarios";

type HealthState = "loading" | "ok" | "fail";

export default function SettingsPage() {
  const backendUrl = getBackendUrl();
  const [health, setHealth] = useState<HealthState>("loading");
  const [healthDetail, setHealthDetail] = useState<string>("");
  const [system, setSystem] = useState<SafeSystemStatus | null>(null);
  const [systemError, setSystemError] = useState<string | null>(null);
  const [localStats, setLocalStats] = useState<LocalDataStats>({
    chatConversations: 0,
    chatMessages: 0,
    pipelineEvents: 0,
    scenarioResults: 0,
  });
  const [recentRooms, setRecentRooms] = useState<string[]>([]);
  const [clearedNote, setClearedNote] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);

  const refreshLocal = useCallback(() => {
    if (typeof window === "undefined") return;
    setLocalStats(readLocalDataStats(localStorage));
    const convs = listConversations(loadChatHistoryStore());
    setRecentRooms(convs.slice(0, 5).map((c) => c.roomId));
  }, []);

  const refreshRemote = useCallback(async () => {
    setHealth("loading");
    setSystemError(null);
    try {
      const [hRes, sRes] = await Promise.all([
        fetch(`${backendUrl}/health`, { cache: "no-store" }),
        fetch(`${backendUrl}/api/v1/system/status`, { cache: "no-store" }),
      ]);
      const h = await hRes.json().catch(() => null);
      if (hRes.ok && h?.status === "ok") {
        setHealth("ok");
        setHealthDetail(typeof h.service === "string" ? h.service : "ok");
      } else {
        setHealth("fail");
        setHealthDetail("Health check failed");
      }

      if (sRes.ok) {
        const raw = await sRes.json();
        setSystem(pickSafeSystemStatus(raw));
      } else {
        setSystem(null);
        setSystemError(`System status HTTP ${sRes.status}`);
      }
    } catch {
      setHealth("fail");
      setHealthDetail("Backend unreachable");
      setSystem(null);
      setSystemError("Could not reach backend");
    }
  }, [backendUrl]);

  useEffect(() => {
    refreshLocal();
    void refreshRemote();
  }, [refreshLocal, refreshRemote]);

  const clearLocalData = () => {
    if (!confirmClear) {
      setConfirmClear(true);
      setClearedNote(null);
      return;
    }
    saveChatHistoryStore({ version: 2, conversations: [] });
    savePipelineStore({ version: 1, events: [] });
    resetAllScenarioStates();
    setClearedNote("Cleared local chat history, analytics pipeline events, and scenario results.");
    setConfirmClear(false);
    refreshLocal();
  };

  const providers = system?.providers;

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto p-8 space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <SettingsIcon className="w-6 h-6 text-slate-300" />
              Settings
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              Connection targets and safe configuration status. Secrets are never shown.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void refreshRemote()}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-700 text-xs text-slate-300 hover:bg-slate-800"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </button>
        </div>

        <div className="glass-card rounded-2xl border border-slate-800 p-5 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm text-slate-200">
              <Server className="w-4 h-4 text-purple-400" />
              Backend URL
            </div>
            <code className="text-xs font-mono text-slate-400 truncate max-w-[55%]">
              {backendUrl}
            </code>
          </div>
          <p className="text-[11px] text-slate-500">
            Set via <code className="text-slate-400">NEXT_PUBLIC_BACKEND_URL</code> at build/dev
            time. No in-browser override (avoids leaking alternate endpoints into a half-configured
            client).
          </p>

          <div className="flex items-center justify-between py-2 border-t border-slate-800">
            <span className="text-sm text-slate-300">Health</span>
            <span className="flex items-center gap-1.5 text-xs font-semibold">
              {health === "loading" && <span className="text-slate-400">Checking…</span>}
              {health === "ok" && (
                <>
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span className="text-emerald-400">Connected</span>
                  {healthDetail ? (
                    <span className="text-slate-500 font-normal">({healthDetail})</span>
                  ) : null}
                </>
              )}
              {health === "fail" && (
                <>
                  <XCircle className="w-4 h-4 text-rose-400" />
                  <span className="text-rose-400">{healthDetail || "Unreachable"}</span>
                </>
              )}
            </span>
          </div>
        </div>

        <div className="glass-card rounded-2xl border border-slate-800 p-5 space-y-3">
          <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <Layers className="w-4 h-4 text-cyan-400" />
            Provider configuration (flags only)
          </h2>
          {systemError && !system ? (
            <p className="text-xs text-rose-400 flex items-center gap-1.5">
              <AlertCircle className="w-3.5 h-3.5" />
              {systemError}
            </p>
          ) : null}
          {system ? (
            <dl className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <dt className="text-slate-500">Service</dt>
                <dd className="text-slate-200">{system.service || "—"}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Version</dt>
                <dd className="text-slate-200">{system.version || "—"}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Environment</dt>
                <dd className="text-slate-200">{system.environment || "—"}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Status</dt>
                <dd className="text-slate-200">{system.status || "—"}</dd>
              </div>
              <div>
                <dt className="text-slate-500">LiveKit configured</dt>
                <dd className="text-slate-200">
                  {providers?.livekit_configured ? "yes" : "no"}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Sarvam configured</dt>
                <dd className="text-slate-200">
                  {providers?.sarvam_configured ? "yes" : "no"}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">LLM configured</dt>
                <dd className="text-slate-200">{providers?.llm_configured ? "yes" : "no"}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Primary / fallback</dt>
                <dd className="text-slate-200">
                  {providers?.primary_provider || "—"}
                  {providers?.fallback_enabled
                    ? ` → ${providers?.fallback_provider || "—"}`
                    : " (fallback off)"}
                </dd>
              </div>
            </dl>
          ) : health === "loading" ? (
            <p className="text-xs text-slate-500">Loading system status…</p>
          ) : (
            <p className="text-xs text-slate-500">System status unavailable.</p>
          )}
        </div>

        <div className="glass-card rounded-2xl border border-slate-800 p-5 space-y-3">
          <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <Wifi className="w-4 h-4 text-slate-400" />
            Session / pipeline (this browser)
          </h2>
          <p className="text-xs text-slate-500">
            LiveKit connection and live STT/LLM/TTS chips are available inside{" "}
            <Link href="/room/demo" className="text-purple-300 hover:text-purple-200">
              Voice Room
            </Link>{" "}
            while connected. This page shows durable local session leftovers only.
          </p>
          <dl className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <dt className="text-slate-500">Stored conversations</dt>
              <dd className="text-slate-200 tabular-nums">{localStats.chatConversations}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Stored messages</dt>
              <dd className="text-slate-200 tabular-nums">{localStats.chatMessages}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Pipeline events</dt>
              <dd className="text-slate-200 tabular-nums">{localStats.pipelineEvents}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Scenario results</dt>
              <dd className="text-slate-200 tabular-nums">{localStats.scenarioResults}</dd>
            </div>
          </dl>
          {recentRooms.length > 0 ? (
            <div className="pt-2 border-t border-slate-800">
              <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5">
                Recent rooms
              </p>
              <ul className="space-y-1">
                {recentRooms.map((r) => (
                  <li key={r} className="text-xs font-mono text-slate-300">
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-xs text-slate-500">No local rooms stored yet.</p>
          )}
        </div>

        <div className="glass-card rounded-2xl border border-slate-800 p-5 space-y-3">
          <h2 className="text-sm font-semibold text-slate-200">Local data</h2>
          <p className="text-xs text-slate-500">
            Clears browser-local chat history, analytics pipeline ids, and scenario evaluation
            state. Does not touch server providers or credentials.
          </p>
          {confirmClear ? (
            <div className="rounded-xl border border-amber-800/50 bg-amber-950/30 p-3 space-y-3">
              <p className="text-xs text-amber-200">
                This permanently removes local conversation history and scenario results from this
                browser. Continue?
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={clearLocalData}
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-rose-700/80 hover:bg-rose-600 text-white text-xs font-semibold"
                >
                  <Trash2 className="w-3.5 h-3.5" aria-hidden />
                  Yes, clear local data
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmClear(false)}
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-700 text-slate-300 text-xs font-semibold hover:bg-slate-800"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={clearLocalData}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-rose-950/50 border border-rose-800/50 text-rose-300 text-xs font-semibold hover:bg-rose-900/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500/50"
            >
              <Trash2 className="w-3.5 h-3.5" aria-hidden />
              Clear local history & analytics
            </button>
          )}
          {clearedNote ? <p className="text-[11px] text-emerald-400" role="status">{clearedNote}</p> : null}
        </div>
      </div>
    </AppShell>
  );
}
