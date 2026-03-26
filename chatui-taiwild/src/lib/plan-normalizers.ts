"use client";

import type {
  ClawhubPlanSuggestion,
  ExecutionChecklistItem,
  ExecutionPlan,
  ExecutionPlanStep,
} from "@/app/components/modalTypes";
import type { ExecutionMode, Strategy } from "@/lib/app-enums";
import { EXECUTION_MODES, STRATEGY_VALUES } from "@/lib/app-enums";

export function normalizeClawhubSuggestions(raw: unknown): ClawhubPlanSuggestion[] {
  if (!Array.isArray(raw)) return [];
  const levels = new Set(["low", "medium", "high"]);
  const recs = new Set(["adopt", "review", "avoid"]);
  const out: ClawhubPlanSuggestion[] = [];
  for (const x of raw) {
    if (!x || typeof x !== "object") continue;
    const o = x as Record<string, unknown>;
    const slug = String(o.slug ?? "").trim();
    if (!slug) continue;
    const rl = String(o.riskLevel ?? "low");
    const rc = String(o.recommendation ?? "review");
    const item: ClawhubPlanSuggestion = {
      slug,
      name: String(o.name ?? slug),
      summary: String(o.summary ?? ""),
      riskLevel: (levels.has(rl) ? rl : "low") as ClawhubPlanSuggestion["riskLevel"],
      recommendation: (recs.has(rc) ? rc : "review") as ClawhubPlanSuggestion["recommendation"],
      analysis: String(o.analysis ?? ""),
      userSelected: Boolean(o.userSelected),
    };
    if (typeof o.score === "number") item.score = o.score;
    out.push(item);
  }
  return out;
}

export function normalizeExecutionPlan(raw: unknown, fallbackLines: string[], mode: Strategy): ExecutionPlan {
  const fallback: ExecutionPlan = {
    planId: `plan_local_${Date.now()}`,
    mode,
    steps: fallbackLines
      .filter((x) => x.trim().length > 0)
      .map((line, idx) => ({
        id: `s${idx + 1}`,
        type: "llm",
        action: line,
        input: { text: line },
        dependsOn: idx > 0 ? [`s${idx}`] : [],
        agent: mode,
        skills: [],
      })),
  };
  if (!raw || typeof raw !== "object") return fallback;
  const o = raw as Record<string, unknown>;
  const modeRaw = String(o.mode ?? mode);
  const validMode: Strategy = STRATEGY_VALUES.includes(modeRaw as Strategy)
    ? (modeRaw as Strategy)
    : mode;
  const rawSteps = Array.isArray(o.steps) ? o.steps : [];
  const steps: ExecutionPlanStep[] = rawSteps.flatMap((x, idx) => {
    if (!x || typeof x !== "object") return [];
    const s = x as Record<string, unknown>;
    const action = String(s.action ?? "").trim();
    if (!action) return [];
    const step: ExecutionPlanStep = {
      id: String(s.id ?? `s${idx + 1}`),
      type: String(s.type ?? "llm"),
      action,
      input: s.input && typeof s.input === "object" ? (s.input as Record<string, unknown>) : undefined,
      dependsOn: Array.isArray(s.dependsOn) ? s.dependsOn.map((d) => String(d)) : undefined,
      agent: s.agent ? String(s.agent) : undefined,
      skills: Array.isArray(s.skills) ? s.skills.map((k) => String(k)) : undefined,
      outputSchema:
        s.outputSchema && typeof s.outputSchema === "object"
          ? (s.outputSchema as Record<string, unknown>)
          : undefined,
    };
    return [step];
  });
  return {
    planId: String(o.planId ?? `plan_local_${Date.now()}`),
    mode: validMode,
    steps: steps.length > 0 ? steps : fallback.steps,
  };
}

export function normalizeStoredExecutionMode(raw: unknown): ExecutionMode {
  return raw === EXECUTION_MODES.USER_EXEC || raw === EXECUTION_MODES.AUTO_EXEC ? raw : EXECUTION_MODES.AUTO_EXEC;
}

export function normalizeStoredTaskChecklist(raw: unknown): ExecutionChecklistItem[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((x) => {
      const itemX = x as { id?: string; text?: string; done?: boolean };
      return {
        id: String(itemX?.id ?? `legacy_${Math.random().toString(16).slice(2)}`),
        text: String(itemX?.text ?? ""),
        done: Boolean(itemX?.done),
      };
    })
    .filter((x) => x.text.trim().length > 0);
}
