"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  FlaskConical,
  Play,
  RotateCcw,
  ExternalLink,
  CheckCircle2,
  XCircle,
  Circle,
  Loader2,
  Users,
  Mic,
  ClipboardCopy,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import {
  ASSIGNMENT_SCENARIOS,
  evaluateAllScenarios,
  loadScenarioResults,
  markScenarioRunning,
  resetAllScenarioStates,
  resetScenarioState,
  roomDeepLink,
  runScenarioEvaluation,
  type ScenarioDefinition,
  type ScenarioResultsStore,
  type ScenarioRunState,
  type ScenarioStatus,
} from "@/lib/testScenarios";

function StatusBadge({
  status,
  execution,
}: {
  status: ScenarioStatus;
  execution?: "interactive" | "manual";
}) {
  const display: ScenarioStatus | "MANUAL" =
    status === "NOT_RUN" && execution === "manual" ? "MANUAL" : status;
  const Icon =
    display === "PASS"
      ? CheckCircle2
      : display === "FAIL"
        ? XCircle
        : display === "RUNNING"
          ? Loader2
          : display === "MANUAL"
            ? Users
            : Circle;
  const tone =
    display === "PASS"
      ? "text-emerald-400 border-emerald-800/60 bg-emerald-950/40"
      : display === "FAIL"
        ? "text-rose-400 border-rose-800/60 bg-rose-950/40"
        : display === "RUNNING"
          ? "text-amber-300 border-amber-800/60 bg-amber-950/40"
          : display === "MANUAL"
            ? "text-amber-300 border-amber-800/60 bg-amber-950/30"
            : "text-slate-400 border-slate-700/60 bg-slate-900/40";
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-lg border ${tone}`}
    >
      <Icon className={`w-3 h-3 ${display === "RUNNING" ? "animate-spin" : ""}`} aria-hidden />
      {display === "NOT_RUN" ? "NOT RUN" : display}
    </span>
  );
}

function ScenarioCard({
  scenario,
  state,
  onLaunch,
  onEvaluate,
  onReset,
}: {
  scenario: ScenarioDefinition;
  state: ScenarioRunState;
  onLaunch: (s: ScenarioDefinition, name?: string) => void;
  onEvaluate: (id: ScenarioDefinition["id"]) => void;
  onReset: (id: ScenarioDefinition["id"]) => void;
}) {
  const copyPrompt = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => undefined);
  };

  return (
    <div className="glass-card rounded-2xl border border-slate-800 p-5 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1 min-w-0">
          <h2 className="text-sm font-semibold text-white">{scenario.name}</h2>
          <p className="text-xs text-slate-400 leading-relaxed">{scenario.purpose}</p>
        </div>
        <StatusBadge status={state.status} execution={scenario.execution} />
      </div>

      <div className="flex flex-wrap gap-2 text-[10px] uppercase tracking-wider">
        {scenario.execution === "manual" ? (
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-amber-950/50 text-amber-300 border border-amber-800/40">
            {scenario.id === "barge-in" ? (
              <Mic className="w-3 h-3" />
            ) : (
              <Users className="w-3 h-3" />
            )}
            Manual / interactive
          </span>
        ) : (
          <span className="px-2 py-1 rounded-md bg-cyan-950/40 text-cyan-300 border border-cyan-800/40">
            Interactive room
          </span>
        )}
        <span className="px-2 py-1 rounded-md bg-slate-900 text-slate-400 border border-slate-700 font-mono normal-case tracking-normal">
          {scenario.roomId}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
        <div className="space-y-2">
          <h3 className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
            Input / steps
          </h3>
          <ol className="list-decimal list-inside space-y-1 text-slate-300">
            {scenario.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          <div className="space-y-1.5 pt-1">
            {scenario.prompts.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => copyPrompt(p)}
                className="w-full flex items-start gap-2 text-left px-2.5 py-2 rounded-lg bg-slate-950/60 border border-slate-800 hover:border-purple-700/50 text-purple-200 font-mono text-[11px]"
                title="Copy prompt"
              >
                <ClipboardCopy className="w-3 h-3 mt-0.5 flex-shrink-0 text-slate-500" />
                <span className="min-w-0 break-words">&ldquo;{p}&rdquo;</span>
              </button>
            ))}
          </div>
        </div>
        <div className="space-y-2">
          <h3 className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
            Expected behavior
          </h3>
          <ul className="space-y-1.5 text-slate-300">
            {scenario.expected.map((e) => (
              <li key={e} className="flex gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-slate-600 flex-shrink-0 mt-0.5" />
                <span>{e}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {state.observed ? (
        <div className="rounded-xl border border-slate-800 bg-slate-950/50 px-3 py-2.5 space-y-1">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
            Observed result
          </p>
          <p className="text-xs text-slate-300 leading-relaxed">{state.observed}</p>
          {state.checks && state.checks.length > 0 ? (
            <ul className="pt-1 space-y-0.5">
              {state.checks.map((c) => (
                <li
                  key={c.id}
                  className={`text-[11px] font-mono ${c.ok ? "text-emerald-400/90" : "text-rose-400/90"}`}
                >
                  {c.ok ? "✓" : "✗"} {c.label}: {c.detail}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : (
        <p className="text-[11px] text-slate-500">
          Not evaluated yet. Open the room, complete the steps, then Evaluate — PASS only when
          local chat/orchestration evidence matches.
        </p>
      )}

      <div className="flex flex-wrap gap-2 pt-1">
        <button
          type="button"
          onClick={() => onLaunch(scenario)}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-cyan-600/80 hover:bg-cyan-500 text-white text-xs font-semibold transition-all"
        >
          <Play className="w-3.5 h-3.5" />
          Open room ({scenario.launchName})
        </button>
        {scenario.secondaryName ? (
          <button
            type="button"
            onClick={() => onLaunch(scenario, scenario.secondaryName)}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-100 text-xs font-semibold border border-slate-700 transition-all"
          >
            <Users className="w-3.5 h-3.5" />
            Open as {scenario.secondaryName}
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => onEvaluate(scenario.id)}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-purple-700/70 hover:bg-purple-600 text-white text-xs font-semibold transition-all"
        >
          <FlaskConical className="w-3.5 h-3.5" />
          Evaluate
        </button>
        <button
          type="button"
          onClick={() => onReset(scenario.id)}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-transparent hover:bg-slate-800 text-slate-400 text-xs font-semibold border border-slate-700 transition-all"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          Reset
        </button>
        <a
          href={roomDeepLink(scenario)}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-slate-200 border border-transparent hover:border-slate-700"
        >
          <ExternalLink className="w-3.5 h-3.5" />
          Room link
        </a>
      </div>
    </div>
  );
}

function defaultState(): ScenarioRunState {
  return { status: "NOT_RUN", observed: "" };
}

export default function TestScenariosPage() {
  const router = useRouter();
  const [results, setResults] = useState<ScenarioResultsStore>({ version: 1, byId: {} });

  const refresh = useCallback(() => {
    setResults(loadScenarioResults());
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const onLaunch = (scenario: ScenarioDefinition, name?: string) => {
    const prompt = scenario.prompts[0];
    if (prompt) navigator.clipboard.writeText(prompt).catch(() => undefined);
    markScenarioRunning(scenario.id);
    refresh();
    router.push(roomDeepLink(scenario, name));
  };

  const onEvaluate = (id: ScenarioDefinition["id"]) => {
    runScenarioEvaluation(id);
    refresh();
  };

  const onReset = (id: ScenarioDefinition["id"]) => {
    resetScenarioState(id);
    refresh();
  };

  const onEvaluateAll = () => {
    evaluateAllScenarios();
    refresh();
  };

  const onResetAll = () => {
    resetAllScenarioStates();
    refresh();
  };

  return (
    <AppShell>
      <div className="max-w-4xl mx-auto p-8 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <FlaskConical className="w-6 h-6 text-cyan-400" />
              Test Scenarios
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              Assignment validation console. Open the real voice room, run the steps, then Evaluate
              against local chat history and orchestration metadata — never fake PASS.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onEvaluateAll}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-purple-700/70 hover:bg-purple-600 text-white text-xs font-semibold"
              title="Safely evaluates all scenarios from local session data (does not auto-join rooms)"
            >
              <FlaskConical className="w-3.5 h-3.5" />
              Run All (evaluate)
            </button>
            <button
              type="button"
              onClick={onResetAll}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-700 text-slate-300 text-xs font-semibold hover:bg-slate-800"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Reset all
            </button>
          </div>
        </div>

        <div className="glass-card rounded-2xl border border-slate-800 p-4 text-xs text-slate-400 space-y-1">
          <p>
            <span className="text-slate-200 font-semibold">How scoring works:</span> Evaluate reads
            the scenario room&apos;s stored turns (eligibility, routing, AI replies). PASS requires
            every expected check to match real data.
          </p>
          <p>
            Multi-user and barge-in are <span className="text-amber-300">manual</span> — they will
            not PASS without observed evidence (dual browsers / cancel pipeline events).
          </p>
        </div>

        <div className="space-y-4">
          {ASSIGNMENT_SCENARIOS.map((scenario) => (
            <ScenarioCard
              key={scenario.id}
              scenario={scenario}
              state={results.byId[scenario.id] || defaultState()}
              onLaunch={onLaunch}
              onEvaluate={onEvaluate}
              onReset={onReset}
            />
          ))}
        </div>
      </div>
    </AppShell>
  );
}
