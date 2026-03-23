"use client";

import AppButton from "@/components/ui/AppButton";
import AppModal from "@/components/ui/AppModal";
import type { CapabilityTool } from "@/app/components/modalTypes";
import { parseToolArgs, ToolPluginHost, ToolResultRenderer } from "@/app/components/toolPlugins";

type Props = {
  open: boolean;
  onClose: () => void;
  tenantId: string;
  ragScopes: string[];
  onOpenRagViewer: () => void;
  tools: CapabilityTool[];
  selectedToolId: string;
  onSelectTool: (toolId: string) => void;
  argsText: string;
  setArgsText: (value: string) => void;
  loading: boolean;
  response: Record<string, unknown> | null;
  error: string | null;
  onInvoke: () => Promise<void>;
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

export default function ToolPlaygroundModal(props: Props) {
  if (!props.open) return null;

  const selectedTool = props.tools.find((tool) => tool.id === props.selectedToolId) ?? null;
  const parsedArgs = parseToolArgs(props.argsText);

  return (
    <AppModal panelClassName="w-full max-w-[95vw] h-[88vh] bg-white dark:bg-zinc-900 rounded border border-zinc-300 dark:border-zinc-700 flex flex-col">
      <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-700 flex items-center gap-2">
        <div className="font-medium flex-1">Tool Playground</div>
        <AppButton type="button" onClick={props.onClose}>
          关闭
        </AppButton>
      </div>

      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[260px_1fr_1fr]">
        <aside className="border-r border-zinc-200 dark:border-zinc-700 p-3 overflow-auto">
          <div className="text-sm font-medium mb-2">Tools</div>
          <div className="space-y-2">
            {props.tools.map((tool) => (
              <button
                key={tool.id}
                type="button"
                className={`w-full text-left rounded border px-2 py-2 ${
                  props.selectedToolId === tool.id
                    ? "border-zinc-500 bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100"
                    : "border-zinc-200 dark:border-zinc-700"
                }`}
                onClick={() => props.onSelectTool(tool.id)}
              >
                <div className="text-sm font-medium">{tool.name}</div>
                <div className="text-[11px] font-mono text-zinc-500">{tool.id}</div>
                <div className="text-xs text-zinc-500 mt-1">{tool.description}</div>
              </button>
            ))}
            {!props.tools.length ? <div className="text-xs text-zinc-500">暂无 tools。</div> : null}
          </div>
        </aside>

        <section className="border-r border-zinc-200 dark:border-zinc-700 p-3 overflow-auto">
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-medium">Args</div>
            <AppButton
              type="button"
              size="sm"
              variant="success"
              loading={props.loading}
              loadingText="Invoking..."
              disabled={!selectedTool}
              onClick={() => void props.onInvoke()}
            >
              Invoke
            </AppButton>
          </div>

          {selectedTool ? (
            <>
              <div className="mt-2 text-xs text-zinc-500">
                {selectedTool.category || "general"} | {selectedTool.allowlisted ? "allowlisted" : "not allowlisted"}
              </div>
              <ToolPluginHost
                tool={selectedTool}
                args={parsedArgs}
                setArgs={(nextArgs) => props.setArgsText(JSON.stringify(nextArgs, null, 2))}
                context={{
                  tenantId: props.tenantId,
                  ragScopes: props.ragScopes,
                  onOpenRagViewer: props.onOpenRagViewer,
                }}
              />
              {Array.isArray(selectedTool.requiredUserInputs) && selectedTool.requiredUserInputs.length > 0 ? (
                <div className="mt-3 rounded border border-zinc-200 dark:border-zinc-700 p-2">
                  <div className="text-xs text-zinc-500 mb-1">Required Inputs</div>
                  <div className="space-y-1">
                    {selectedTool.requiredUserInputs.map((item) => (
                      <div key={`${selectedTool.id}-${item.key}`} className="text-xs">
                        <span className="font-medium">{item.label || item.key}</span>
                        <span className="text-zinc-500"> ({item.type || "text"}{item.required ? ", required" : ""}{item.secret ? ", secret" : ""})</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
              {selectedTool.inputSchema ? (
                <details className="mt-3 rounded border border-zinc-200 dark:border-zinc-700 p-2">
                  <summary className="cursor-pointer text-xs text-zinc-500">Input Schema</summary>
                  <pre className="mt-2 text-[11px] whitespace-pre-wrap break-words">{pretty(selectedTool.inputSchema)}</pre>
                </details>
              ) : null}
            </>
          ) : (
            <div className="mt-2 text-xs text-zinc-500">选择一个 tool。</div>
          )}

          <details className="mt-3 rounded border border-zinc-200 dark:border-zinc-700">
            <summary className="cursor-pointer px-3 py-2 text-xs text-zinc-500">Raw JSON Args</summary>
            <div className="border-t border-zinc-200 dark:border-zinc-700 p-3">
              <textarea
                className="w-full min-h-[40vh] rounded border border-zinc-300 dark:border-zinc-700 px-3 py-2 text-xs font-mono bg-white dark:bg-zinc-900"
                value={props.argsText}
                onChange={(e) => props.setArgsText(e.target.value)}
                placeholder='{"query":"workflow"}'
              />
            </div>
          </details>
        </section>

        <section className="p-3 overflow-auto">
          <div className="text-sm font-medium">Request / Response</div>
          {props.error ? <div className="mt-2 text-xs text-red-600">{props.error}</div> : null}
          <div className="mt-3 rounded border border-zinc-200 dark:border-zinc-700 p-2">
            <div className="text-xs text-zinc-500 mb-1">Resolved Request</div>
            <pre className="text-[11px] whitespace-pre-wrap break-words">
              {pretty({
                toolId: props.selectedToolId || null,
                args: (() => {
                  try {
                    return JSON.parse(props.argsText || "{}");
                  } catch {
                    return props.argsText;
                  }
                })(),
              })}
            </pre>
          </div>
          {selectedTool ? <ToolResultRenderer tool={selectedTool} response={props.response} /> : null}
          <details className="mt-3 rounded border border-zinc-200 dark:border-zinc-700 p-2">
            <summary className="cursor-pointer text-xs text-zinc-500">Raw Response</summary>
            <pre className="mt-2 text-[11px] whitespace-pre-wrap break-words">{pretty(props.response)}</pre>
          </details>
        </section>
      </div>
    </AppModal>
  );
}
