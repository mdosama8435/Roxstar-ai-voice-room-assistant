"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  BarChart2,
  Activity,
  Bot,
  Clock,
  MessageSquare,
  Mic,
  Route,
  Users,
  Wifi,
  Layers,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import {
  type AnalyticsSnapshot,
  ANALYTICS_PIPELINE_STORAGE_KEY,
  formatDuration,
  loadAnalyticsSnapshot,
} from "@/lib/analytics";
import { CHAT_HISTORY_STORAGE_KEY } from "@/lib/chatHistory";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

function formatWhen(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

function StatCard({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  detail?: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="glass-card rounded-2xl border border-slate-800 p-5 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
          {label}
        </span>
        <Icon className="w-4 h-4 text-slate-500" />
      </div>
      <p className="text-2xl font-bold text-white tabular-nums">{value}</p>
      {detail ? <p className="text-xs text-slate-500">{detail}</p> : null}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="glass-card rounded-2xl border border-slate-800 border-dashed p-10 text-center space-y-3">
      <BarChart2 className="w-10 h-10 text-slate-600 mx-auto" />
      <h2 className="text-lg font-semibold text-slate-200">No analytics yet</h2>
      <p className="text-sm text-slate-400 max-w-md mx-auto">
        Join a Voice Room and complete conversation turns. Metrics appear here from
        real local session data — nothing is invented ahead of time.
      </p>
    </div>
  );
}

export default function AnalyticsPage() {
  const [snapshot, setSnapshot] = useState<AnalyticsSnapshot | null>(null);
  const [scopeRoomId, setScopeRoomId] = useState<string | null>(null);
  const [backendOk, setBackendOk] = useState<boolean | null>(null);

  const refresh = useCallback(() => {
    setSnapshot(loadAnalyticsSnapshot({ roomId: scopeRoomId }));
  }, [scopeRoomId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (
        e.key === CHAT_HISTORY_STORAGE_KEY ||
        e.key === ANALYTICS_PIPELINE_STORAGE_KEY ||
        e.key === null
      ) {
        refresh();
      }
    };
    window.addEventListener("storage", onStorage);
    const onFocus = () => refresh();
    window.addEventListener("focus", onFocus);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("focus", onFocus);
    };
  }, [refresh]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/health`, { cache: "no-store" });
        const data = await res.json();
        if (!cancelled) setBackendOk(res.ok && data?.status === "ok");
      } catch {
        if (!cancelled) setBackendOk(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const allSessionsSnapshot = useMemo(
    () => (scopeRoomId ? loadAnalyticsSnapshot({ roomId: null }) : snapshot),
    [scopeRoomId, snapshot]
  );

  const roomOptions = allSessionsSnapshot?.recentSessions.map((s) => s.roomId) ?? [];

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto p-8 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <BarChart2 className="w-6 h-6 text-purple-400" />
              Analytics
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              Real session metrics from local conversation and pipeline events.
            </p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <Wifi
                className={`w-3.5 h-3.5 ${
                  backendOk === true
                    ? "text-emerald-400"
                    : backendOk === false
                      ? "text-rose-400"
                      : "text-slate-500"
                }`}
              />
              Backend{" "}
              {backendOk === null ? "…" : backendOk ? "online" : "offline"}
            </div>
            {roomOptions.length > 0 ? (
              <select
                className="bg-slate-900/80 border border-slate-700 rounded-lg text-xs text-slate-200 px-3 py-2"
                value={scopeRoomId ?? ""}
                onChange={(e) => setScopeRoomId(e.target.value || null)}
                aria-label="Filter by room"
              >
                <option value="">All sessions</option>
                {roomOptions.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            ) : null}
          </div>
        </div>

        {!snapshot || !snapshot.hasData ? (
          <EmptyState />
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard
                label="Total turns"
                value={snapshot.totalTurns}
                detail={
                  snapshot.scopeRoomId
                    ? `Room ${snapshot.scopeRoomId}`
                    : `${snapshot.sessionCount} session${snapshot.sessionCount === 1 ? "" : "s"}`
                }
                icon={MessageSquare}
              />
              <StatCard
                label="Human turns"
                value={snapshot.humanTurns}
                icon={Users}
              />
              <StatCard
                label="AI responses"
                value={snapshot.aiResponses}
                detail={
                  snapshot.dostResponses + snapshot.sathiResponses > 0
                    ? `Dost ${snapshot.dostResponses} · Sathi ${snapshot.sathiResponses}`
                    : undefined
                }
                icon={Bot}
              />
              {typeof snapshot.avgAiLatencyMs === "number" ? (
                <StatCard
                  label="Avg AI latency"
                  value={`${snapshot.avgAiLatencyMs} ms`}
                  detail={`From ${snapshot.aiLatencySampleCount} timed response${
                    snapshot.aiLatencySampleCount === 1 ? "" : "s"
                  }`}
                  icon={Clock}
                />
              ) : (
                <StatCard
                  label="Sessions"
                  value={snapshot.sessionCount}
                  icon={Layers}
                />
              )}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="glass-card rounded-2xl border border-slate-800 p-5 space-y-4">
                <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-cyan-400" />
                  Conversation activity
                </h2>
                <dl className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <dt className="text-xs text-slate-500 uppercase tracking-wider">Human</dt>
                    <dd className="text-lg font-semibold text-white tabular-nums">
                      {snapshot.humanTurns}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500 uppercase tracking-wider">AI</dt>
                    <dd className="text-lg font-semibold text-white tabular-nums">
                      {snapshot.aiResponses}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500 uppercase tracking-wider">AI Dost</dt>
                    <dd className="text-lg font-semibold text-purple-300 tabular-nums">
                      {snapshot.dostResponses}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500 uppercase tracking-wider">AI Sathi</dt>
                    <dd className="text-lg font-semibold text-pink-300 tabular-nums">
                      {snapshot.sathiResponses}
                    </dd>
                  </div>
                </dl>
                {typeof snapshot.eligibleTurns === "number" &&
                typeof snapshot.nonEligibleTurns === "number" ? (
                  <div className="pt-3 border-t border-slate-800/80 grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <dt className="text-xs text-slate-500 uppercase tracking-wider">
                        Eligible
                      </dt>
                      <dd className="text-base font-semibold text-emerald-300 tabular-nums">
                        {snapshot.eligibleTurns}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs text-slate-500 uppercase tracking-wider">
                        Non-eligible
                      </dt>
                      <dd className="text-base font-semibold text-slate-300 tabular-nums">
                        {snapshot.nonEligibleTurns}
                      </dd>
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="glass-card rounded-2xl border border-slate-800 p-5 space-y-4">
                <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                  <Route className="w-4 h-4 text-purple-400" />
                  AI routing breakdown
                </h2>
                {typeof snapshot.routedToDost === "number" ? (
                  <dl className="grid grid-cols-3 gap-3 text-sm">
                    <div>
                      <dt className="text-xs text-slate-500 uppercase tracking-wider">→ Dost</dt>
                      <dd className="text-lg font-semibold text-purple-300 tabular-nums">
                        {snapshot.routedToDost}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs text-slate-500 uppercase tracking-wider">→ Sathi</dt>
                      <dd className="text-lg font-semibold text-pink-300 tabular-nums">
                        {snapshot.routedToSathi}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs text-slate-500 uppercase tracking-wider">Silence</dt>
                      <dd className="text-lg font-semibold text-slate-300 tabular-nums">
                        {snapshot.routedNone}
                      </dd>
                    </div>
                  </dl>
                ) : (
                  <p className="text-sm text-slate-500">
                    Routing counts appear after orchestration metadata is recorded on turns.
                  </p>
                )}
                <div className="pt-3 border-t border-slate-800/80 grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <dt className="text-xs text-slate-500 uppercase tracking-wider">
                      Dost replies
                    </dt>
                    <dd className="text-base font-semibold text-white tabular-nums">
                      {snapshot.dostResponses}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500 uppercase tracking-wider">
                      Sathi replies
                    </dt>
                    <dd className="text-base font-semibold text-white tabular-nums">
                      {snapshot.sathiResponses}
                    </dd>
                  </div>
                </div>
              </div>
            </div>

            {snapshot.pipeline ? (
              <div className="glass-card rounded-2xl border border-slate-800 p-5 space-y-4">
                <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                  <Mic className="w-4 h-4 text-cyan-400" />
                  Pipeline / event summary
                </h2>
                <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                  <div>
                    <dt className="text-xs text-slate-500 uppercase tracking-wider">STT final</dt>
                    <dd className="text-lg font-semibold text-white tabular-nums">
                      {snapshot.pipeline.sttFinal}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500 uppercase tracking-wider">STT remote</dt>
                    <dd className="text-lg font-semibold text-white tabular-nums">
                      {snapshot.pipeline.sttRemote}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500 uppercase tracking-wider">
                      Orchestration
                    </dt>
                    <dd className="text-lg font-semibold text-white tabular-nums">
                      {snapshot.pipeline.orchestration}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500 uppercase tracking-wider">AI response</dt>
                    <dd className="text-lg font-semibold text-white tabular-nums">
                      {snapshot.pipeline.aiResponse}
                    </dd>
                  </div>
                </dl>
              </div>
            ) : null}

            {typeof snapshot.avgAiLatencyMs === "number" ? (
              <div className="glass-card rounded-2xl border border-slate-800 p-5 space-y-2">
                <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                  <Clock className="w-4 h-4 text-amber-400" />
                  Latency
                </h2>
                <p className="text-sm text-slate-300">
                  Average AI response latency{" "}
                  <span className="font-semibold text-white tabular-nums">
                    {snapshot.avgAiLatencyMs} ms
                  </span>{" "}
                  across {snapshot.aiLatencySampleCount} timed response
                  {snapshot.aiLatencySampleCount === 1 ? "" : "s"} with recorded{" "}
                  <code className="text-xs text-slate-400">latencyMs</code>.
                </p>
              </div>
            ) : (
              <div className="glass-card rounded-2xl border border-slate-800 p-5 space-y-2">
                <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                  <Clock className="w-4 h-4 text-slate-500" />
                  Latency
                </h2>
                <p className="text-sm text-slate-500">Not available yet — no timed AI responses in local history.</p>
              </div>
            )}

            <div className="glass-card rounded-2xl border border-slate-800 p-5 space-y-4">
              <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                <Layers className="w-4 h-4 text-slate-400" />
                Recent rooms / sessions
              </h2>
              {snapshot.recentSessions.length === 0 ? (
                <p className="text-sm text-slate-500">No sessions in this scope.</p>
              ) : (
                <ul className="divide-y divide-slate-800/80">
                  {snapshot.recentSessions.map((s) => (
                    <li
                      key={s.roomId}
                      className="py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2"
                    >
                      <div>
                        <button
                          type="button"
                          className="text-sm font-medium text-purple-300 hover:text-purple-200 font-mono"
                          onClick={() => setScopeRoomId(s.roomId)}
                        >
                          {s.roomId}
                        </button>
                        <p className="text-xs text-slate-500 mt-0.5">
                          Updated {formatWhen(s.updatedAt)}
                          {typeof s.durationMs === "number"
                            ? ` · ${formatDuration(s.durationMs)}`
                            : ""}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-3 text-xs text-slate-400">
                        <span>{s.messageCount} turns</span>
                        <span>{s.humanTurns} human</span>
                        <span>{s.aiResponses} AI</span>
                        <span>{s.humanParticipantCount} participant{s.humanParticipantCount === 1 ? "" : "s"}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}
