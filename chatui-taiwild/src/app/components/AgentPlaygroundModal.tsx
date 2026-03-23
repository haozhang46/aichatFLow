"use client";

import AppButton from "@/components/ui/AppButton";
import AppModal from "@/components/ui/AppModal";
import type { CapabilityAgent } from "@/app/components/modalTypes";

type Props = {
  open: boolean;
  onClose: () => void;
  agents: CapabilityAgent[];
  selectedAgentId: string;
  onSelectAgent: (agentId: string) => void;
  prompt: string;
  setPrompt: (value: string) => void;
  loading: boolean;
  response: Record<string, unknown> | null;
  error: string | null;
  onInvoke: () => Promise<void>;
};

type AgentPlaygroundResponse = {
  traceId?: unknown;
  latencyMs?: unknown;
  status?: unknown;
  result?: {
    mode?: unknown;
    answer?: unknown;
  } | null;
  stepOutputs?: unknown;
  events?: unknown;
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

/** Registry rows may use `source: { type, path }`; UI must never render objects as React children. */
function formatAgentSource(source: unknown): string {
  if (source == null || source === "") return "built-in";
  if (typeof source === "string") return source;
  if (typeof source === "object" && source !== null) {
    const o = source as { type?: unknown; path?: unknown };
    const t = o.type != null ? String(o.type) : "";
    const p = o.path != null ? String(o.path) : "";
    if (t || p) return [t, p].filter(Boolean).join(" · ");
  }
  try {
    return JSON.stringify(source);
  } catch {
    return String(source);
  }
}

function asObject(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

export default function AgentPlaygroundModal(props: Props) {
  if (!props.open) return null;

  const selectedAgent = props.agents.find((agent) => agent.id === props.selectedAgentId) ?? null;
  const response = (props.response as AgentPlaygroundResponse | null) ?? null;
  const result = asObject(response?.result);
  const stepOutputs = asObject(response?.stepOutputs);
  const events = Array.isArray(response?.events) ? response?.events : [];
  const answer = typeof result?.answer === "string" ? result.answer : null;
  const mode = typeof result?.mode === "string" ? result.mode : null;
  const traceId = typeof response?.traceId === "string" ? response.traceId : null;
  const latencyMs = typeof response?.latencyMs === "number" ? response.latencyMs : null;
  const status = typeof response?.status === "string" ? response.status : null;

  return (
    <AppModal panelClassName="w-full max-w-[95vw] h-[88vh] bg-white dark:bg-zinc-900 rounded border border-zinc-300 dark:border-zinc-700 flex flex-col">
      <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-700 flex items-center gap-2">
        <div className="font-medium flex-1">Agent Playground</div>
        <AppButton type="button" onClick={props.onClose}>
          关闭
        </AppButton>
      </div>

      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[260px_1fr_1fr]">
        <aside className="border-r border-zinc-200 dark:border-zinc-700 p-3 overflow-auto">
          <div className="text-sm font-medium mb-2">Agents</div>
          <div className="space-y-2">
            {props.agents.map((agent) => (
              <button
                key={`${formatAgentSource(agent.source)}-${agent.id}`}
                type="button"
                className={`w-full text-left rounded border px-2 py-2 ${
                  props.selectedAgentId === agent.id
                    ? "border-zinc-500 bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100"
                    : "border-zinc-200 dark:border-zinc-700"
                }`}
                onClick={() => props.onSelectAgent(agent.id)}
              >
                <div className="text-sm font-medium">{agent.label}</div>
                <div className="text-[11px] font-mono text-zinc-500">{agent.id}</div>
                <div className="text-xs text-zinc-500 mt-1">{agent.description}</div>
                <div className="text-[11px] text-zinc-500 mt-1">{formatAgentSource(agent.source)}</div>
              </button>
            ))}
            {!props.agents.length ? <div className="text-xs text-zinc-500">暂无 agents。</div> : null}
          </div>
        </aside>

        <section className="border-r border-zinc-200 dark:border-zinc-700 p-3 overflow-auto">
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-medium">Prompt</div>
            <AppButton
              type="button"
              size="sm"
              variant="success"
              loading={props.loading}
              loadingText="Invoking..."
              disabled={!selectedAgent || !props.prompt.trim()}
              onClick={() => void props.onInvoke()}
            >
              Invoke
            </AppButton>
          </div>

          {selectedAgent ? (
            <div className="mt-2 text-xs text-zinc-500">
              {formatAgentSource(selectedAgent.source)} | {selectedAgent.id}
            </div>
          ) : (
            <div className="mt-2 text-xs text-zinc-500">选择一个 agent。</div>
          )}

          <textarea
            className="mt-3 w-full min-h-[58vh] border border-zinc-300 dark:border-zinc-700 rounded px-3 py-2 text-xs font-mono bg-white dark:bg-zinc-900"
            value={props.prompt}
            onChange={(e) => props.setPrompt(e.target.value)}
            placeholder="Write a short product launch story with a calm tone."
          />
        </section>

        <section className="p-3 overflow-auto">
          <div className="text-sm font-medium">Request / Response</div>
          {props.error ? <div className="mt-2 text-xs text-red-600">{props.error}</div> : null}
          <div className="mt-3 rounded border border-zinc-200 dark:border-zinc-700 p-2">
            <div className="text-xs text-zinc-500 mb-1">Resolved Request</div>
            <pre className="text-[11px] whitespace-pre-wrap break-words">
              {pretty({
                agentId: props.selectedAgentId || null,
                prompt: props.prompt,
              })}
            </pre>
          </div>
          <div className="mt-3 rounded border border-zinc-200 dark:border-zinc-700 p-2">
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-zinc-500 mb-2">
              {status ? <span>Status: {status}</span> : null}
              {mode ? <span>Mode: {mode}</span> : null}
              {latencyMs != null ? <span>Latency: {latencyMs}ms</span> : null}
              {traceId ? <span className="font-mono">Trace: {traceId}</span> : null}
            </div>
            {answer ? (
              <div className="mb-3 rounded border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-950 p-2">
                <div className="text-xs text-zinc-500 mb-1">Answer</div>
                <pre className="text-[11px] whitespace-pre-wrap break-words">{answer}</pre>
              </div>
            ) : null}
            {stepOutputs ? (
              <div className="mb-3 rounded border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-950 p-2">
                <div className="text-xs text-zinc-500 mb-1">Step Outputs</div>
                <pre className="text-[11px] whitespace-pre-wrap break-words">{pretty(stepOutputs)}</pre>
              </div>
            ) : null}
            {events.length ? (
              <div className="mb-3 rounded border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-950 p-2">
                <div className="text-xs text-zinc-500 mb-1">Events</div>
                <pre className="text-[11px] whitespace-pre-wrap break-words">{pretty(events)}</pre>
              </div>
            ) : null}
            <div className="text-xs text-zinc-500 mb-1">Response</div>
            <pre className="text-[11px] whitespace-pre-wrap break-words">{pretty(props.response)}</pre>
          </div>
        </section>
      </div>
    </AppModal>
  );
}
