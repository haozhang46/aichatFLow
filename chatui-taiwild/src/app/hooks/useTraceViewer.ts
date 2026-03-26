"use client";

import { useState } from "react";
import { apiGet } from "@/lib/api-client";

type TraceRun = Record<string, unknown>;

export function useTraceViewer() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [traceId, setTraceId] = useState<string | null>(null);
  const [traceIds, setTraceIds] = useState<string[]>([]);
  const [run, setRun] = useState<TraceRun | null>(null);

  async function loadTrace(nextTraceId: string) {
    setLoading(true);
    setError(null);
    setTraceId(nextTraceId);
    setRun(null);
    try {
      const otieData = await apiGet<{ run?: TraceRun }>(`/v1/otie/runs/${encodeURIComponent(nextTraceId)}`);
      if (otieData?.run) {
        setRun(otieData.run);
        return;
      }

      const traceData = await apiGet<{ events?: Array<Record<string, unknown>> }>(
        `/v1/traces/${encodeURIComponent(nextTraceId)}`
      );
      setRun({
        traceId: nextTraceId,
        runId: nextTraceId,
        status: "legacy-trace",
        finalAnswer: "",
        stepOutputs: {},
        events: Array.isArray(traceData?.events) ? traceData.events : [],
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "load trace failed");
    } finally {
      setLoading(false);
    }
  }

  async function openTrace(nextTraceId: string, requestId?: string) {
    setOpen(true);
    if (requestId) {
      try {
        const data = await apiGet<{ traceIds?: unknown[] }>("/v1/traces", { requestId });
        if (Array.isArray(data?.traceIds)) {
          const ids = data.traceIds.map((x: unknown) => String(x)).filter((x: string) => x.trim().length > 0);
          setTraceIds(ids.length > 0 ? ids : [nextTraceId]);
        } else {
          setTraceIds([nextTraceId]);
        }
      } catch {
        setTraceIds([nextTraceId]);
      }
    } else {
      setTraceIds([nextTraceId]);
    }
    await loadTrace(nextTraceId);
  }

  function closeTrace() {
    setOpen(false);
  }

  return {
    open,
    closeTrace,
    loading,
    error,
    traceId,
    traceIds,
    run,
    loadTrace,
    openTrace,
  };
}
