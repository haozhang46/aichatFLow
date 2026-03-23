"use client";

import { useMemo, useState } from "react";

import AppButton from "@/components/ui/AppButton";
import AppModal from "@/components/ui/AppModal";

type TraceRun = {
  runId?: string;
  traceId?: string;
  status?: string;
  finalAnswer?: string;
  intent?: {
    userQuery?: string;
  };
  plan?: {
    mode?: string;
    steps?: Array<{ stepId?: string; action?: string; kind?: string }>;
  };
  stepOutputs?: Record<string, unknown>;
  events?: Array<Record<string, unknown>>;
};

type Props = {
  open: boolean;
  onClose: () => void;
  loading: boolean;
  traceId: string | null;
  traceIds: string[];
  onSelectTrace: (traceId: string) => void | Promise<void>;
  run: TraceRun | null;
  error: string | null;
};

function pretty(value: unknown) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function TraceModalBody(props: Props) {
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"all" | "step" | "from-step">("all");
  const [fullscreen, setFullscreen] = useState(false);

  const filteredEvents = useMemo(() => {
    const events = props.run?.events ?? [];
    if (!selectedStepId || viewMode === "all") return events;
    if (viewMode === "step") {
      return events.filter((event) => String(event.stepId ?? "") === selectedStepId);
    }
    const startIndex = events.findIndex(
      (event) =>
        String(event.stepId ?? "") === selectedStepId &&
        ["step_started", "loop_tick", "policy_evaluated", "tool_call", "reasoning_result", "schema_checked", "step_completed"].includes(
          String(event.type ?? "")
        )
    );
    return startIndex >= 0 ? events.slice(startIndex) : events.filter((event) => String(event.stepId ?? "") === selectedStepId);
  }, [props.run?.events, selectedStepId, viewMode]);

  const ragHits = useMemo(() => {
    const events = props.run?.events ?? [];
    const selected = events
      .filter((event) => String(event.type ?? "") === "rag_hits_selected")
      .flatMap((event) => (Array.isArray(event.hits) ? event.hits : []));
    return selected.filter((item) => typeof item === "object") as Array<Record<string, unknown>>;
  }, [props.run?.events]);

  async function copyAllLogs() {
    const text = filteredEvents
      .map((event) => {
        try {
          return JSON.stringify(event, null, 2);
        } catch {
          return String(event);
        }
      })
      .join("\n\n");
    if (!text) return;
    await navigator.clipboard.writeText(text);
  }

  if (!props.open) return null;

  return (
    <AppModal
      panelClassName={
        fullscreen
          ? "w-[calc(100vw-1rem)] h-[calc(100vh-1rem)] max-w-none bg-white dark:bg-zinc-900 rounded border border-zinc-300 dark:border-zinc-700 flex flex-col"
          : "w-full max-w-6xl h-[82vh] bg-white dark:bg-zinc-900 rounded border border-zinc-300 dark:border-zinc-700 flex flex-col"
      }
    >
      <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-700 flex items-center gap-2">
        <div className="font-medium flex-1">Trace Viewer</div>
        {props.traceId ? <div className="text-[11px] font-mono text-zinc-500 break-all">{props.traceId}</div> : null}
        <AppButton type="button" size="xs" variant="tab" onClick={() => setFullscreen((prev) => !prev)}>
          {fullscreen ? "Exit Full" : "Fullscreen"}
        </AppButton>
        <AppButton type="button" onClick={props.onClose}>
          关闭
        </AppButton>
      </div>
      <div className="p-4 overflow-auto grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-4">
        <div className="space-y-3 lg:sticky lg:top-0 self-start">
          <div className="border border-zinc-200 dark:border-zinc-700 rounded p-3">
            <div className="text-xs text-zinc-500 mb-2">Trace List</div>
            <div className="space-y-2 max-h-40 overflow-auto">
              {props.traceIds.map((id) => (
                <button
                  key={id}
                  type="button"
                  className={`w-full text-left text-xs border rounded px-2 py-1 ${
                    props.traceId === id
                      ? "border-zinc-500 bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100"
                      : "border-zinc-200 dark:border-zinc-700"
                  }`}
                  onClick={() => void props.onSelectTrace(id)}
                >
                  <div className="font-mono break-all">{id}</div>
                </button>
              ))}
              {props.traceIds.length === 0 ? <div className="text-xs text-zinc-500">暂无 trace 列表。</div> : null}
            </div>
          </div>
          <div className="border border-zinc-200 dark:border-zinc-700 rounded p-3">
            <div className="text-xs text-zinc-500">状态</div>
            <div className="text-sm font-medium">{props.run?.status || "-"}</div>
            {props.run?.intent?.userQuery ? (
              <>
                <div className="text-xs text-zinc-500 mt-3">Query</div>
                <div className="text-sm whitespace-pre-wrap">{props.run.intent.userQuery}</div>
              </>
            ) : null}
            {props.run?.plan?.mode ? (
              <>
                <div className="text-xs text-zinc-500 mt-3">Mode</div>
                <div className="text-sm">{props.run.plan.mode}</div>
              </>
            ) : null}
          </div>
          <div className="border border-zinc-200 dark:border-zinc-700 rounded p-3">
            <div className="text-xs text-zinc-500 mb-2">Steps</div>
            <div className="space-y-2">
              {(props.run?.plan?.steps ?? []).map((step, idx) => (
                <button
                  type="button"
                  key={`${step.stepId ?? idx}`}
                  className={`w-full text-left text-xs border rounded px-2 py-1 ${
                    selectedStepId === (step.stepId ?? `s${idx + 1}`)
                      ? "border-zinc-500 bg-zinc-100 dark:bg-zinc-800"
                      : "border-zinc-200 dark:border-zinc-700"
                  }`}
                  onClick={() =>
                    setSelectedStepId((prev) => (prev === (step.stepId ?? `s${idx + 1}`) ? null : step.stepId ?? `s${idx + 1}`))
                  }
                >
                  <div className="font-medium">
                    {step.stepId ?? `s${idx + 1}`} {step.kind ? `| ${step.kind}` : ""}
                  </div>
                  <div className="text-zinc-500 whitespace-pre-wrap">{step.action ?? ""}</div>
                </button>
              ))}
              {!(props.run?.plan?.steps ?? []).length ? <div className="text-xs text-zinc-500">暂无 step 数据。</div> : null}
            </div>
          </div>
        </div>
        <div className="space-y-3">
          <div className="border border-zinc-200 dark:border-zinc-700 rounded p-3">
            <div className="text-xs text-zinc-500 mb-2">Final Answer</div>
            {props.loading ? <div className="text-sm text-zinc-500">加载中...</div> : null}
            {props.error ? <div className="text-sm text-red-600">{props.error}</div> : null}
            {!props.loading && !props.error ? (
              <pre className="text-xs whitespace-pre-wrap break-words">{props.run?.finalAnswer || "-"}</pre>
            ) : null}
          </div>
          <div className="border border-zinc-200 dark:border-zinc-700 rounded p-3">
            <div className="text-xs text-zinc-500 mb-2">Step Outputs</div>
            <pre className="text-xs whitespace-pre-wrap break-words">{pretty(props.run?.stepOutputs ?? {})}</pre>
          </div>
          <div className="border border-zinc-200 dark:border-zinc-700 rounded p-3">
            <div className="text-xs text-zinc-500 mb-2">RAG Hits</div>
            <div className="space-y-2 max-h-56 overflow-auto">
              {ragHits.map((hit, idx) => (
                <div key={`${String(hit.chunkId ?? hit.documentId ?? idx)}-${idx}`} className="border border-zinc-200 dark:border-zinc-700 rounded px-2 py-2">
                  <div className="text-[11px] font-medium">
                    {String(hit.documentId ?? "unknown")} / {String(hit.chunkId ?? "chunk")}
                  </div>
                  <div className="text-[10px] text-zinc-500">
                    scope={String(hit.scope ?? "")} score={String(hit.score ?? "")}
                  </div>
                </div>
              ))}
              {!ragHits.length ? <div className="text-xs text-zinc-500">暂无 retrieval hits。</div> : null}
            </div>
          </div>
          <div className="border border-zinc-200 dark:border-zinc-700 rounded p-3">
            <div className="flex items-center justify-between gap-2 mb-2">
              <div className="text-xs text-zinc-500">Events</div>
              <div className="flex items-center gap-2">
                <AppButton type="button" size="xs" variant="info" onClick={() => void copyAllLogs()} disabled={!filteredEvents.length}>
                  复制全部日志
                </AppButton>
                <div className="flex items-center gap-1 border border-zinc-200 dark:border-zinc-700 rounded p-0.5">
                  <AppButton type="button" size="xs" variant="tab" className={viewMode === "all" ? "bg-zinc-200 dark:bg-zinc-700" : ""} onClick={() => setViewMode("all")}>
                  全部
                  </AppButton>
                  <AppButton
                    type="button"
                    size="xs"
                    variant="tab"
                    className={viewMode === "step" ? "bg-zinc-200 dark:bg-zinc-700" : ""}
                    onClick={() => setViewMode("step")}
                    disabled={!selectedStepId}
                  >
                    当前 Step
                  </AppButton>
                  <AppButton
                    type="button"
                    size="xs"
                    variant="tab"
                    className={viewMode === "from-step" ? "bg-zinc-200 dark:bg-zinc-700" : ""}
                    onClick={() => setViewMode("from-step")}
                    disabled={!selectedStepId}
                  >
                    从此开始
                  </AppButton>
                </div>
              </div>
            </div>
            <div className="space-y-2 min-h-[70vh] max-h-[70vh] overflow-auto">
              {filteredEvents.map((event, idx) => (
                <div
                  key={`${String(event.type ?? "event")}-${idx}`}
                  className={`border rounded px-2 py-2 ${
                    selectedStepId && String(event.stepId ?? "") === selectedStepId
                      ? "border-zinc-500 bg-zinc-100/90 dark:bg-zinc-800/80"
                      : "border-zinc-200 dark:border-zinc-700"
                  }`}
                >
                  <div className="text-[11px] font-medium text-zinc-700 dark:text-zinc-200">
                    {String(event.type ?? "event")}
                  </div>
                  {event.stepId ? <div className="text-[10px] text-zinc-500">step: {String(event.stepId)}</div> : null}
                  <div className="text-[10px] text-zinc-500">{String(event.ts ?? "")}</div>
                  <pre className="text-[11px] whitespace-pre-wrap break-words mt-1">{pretty(event)}</pre>
                </div>
              ))}
              {!filteredEvents.length && !props.loading ? (
                <div className="text-xs text-zinc-500">暂无事件。</div>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </AppModal>
  );
}

export default function TraceModal(props: Props) {
  if (!props.open) return null;
  return <TraceModalBody key={props.traceId ?? "empty-trace"} {...props} />;
}
