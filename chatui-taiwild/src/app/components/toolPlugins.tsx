"use client";

import type { ReactNode } from "react";
import type { CapabilityTool } from "@/app/components/modalTypes";
import AppButton from "@/components/ui/AppButton";

type ToolPluginContext = {
  tenantId: string;
  ragScopes: string[];
  onOpenRagViewer: () => void;
};

type ToolPluginProps = {
  tool: CapabilityTool;
  args: Record<string, unknown>;
  setArgs: (nextArgs: Record<string, unknown>) => void;
  context: ToolPluginContext;
};

type ToolResultRendererProps = {
  tool: CapabilityTool;
  response: Record<string, unknown> | null;
};

function textValue(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function numberValue(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function objectValue(value: unknown) {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function updateArg(
  args: Record<string, unknown>,
  setArgs: (nextArgs: Record<string, unknown>) => void,
  key: string,
  value: unknown
) {
  const nextArgs = { ...args };
  if (value === "" || value == null) {
    delete nextArgs[key];
  } else {
    nextArgs[key] = value;
  }
  setArgs(nextArgs);
}

function GenericToolFields(props: ToolPluginProps) {
  const fields = props.tool.uiSchema?.fields ?? [];
  if (!fields.length) return null;

  return (
    <div className="mt-3 rounded border border-zinc-200 dark:border-zinc-700 p-3 space-y-2">
      <div className="text-sm font-medium">Tool UI</div>
      {fields.map((field) => {
        const component = field.component || "input";
        const value = props.args[field.key];

        if (component === "textarea") {
          return (
            <label key={field.key} className="block">
              <div className="mb-1 text-[11px] text-zinc-500">{field.label}</div>
              <textarea
                className="w-full rounded border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-900 outline-none transition-colors focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                rows={field.rows ?? 4}
                value={textValue(value)}
                placeholder={field.placeholder || ""}
                onChange={(e) => updateArg(props.args, props.setArgs, field.key, e.target.value)}
              />
            </label>
          );
        }

        if (component === "number") {
          return (
            <label key={field.key} className="block">
              <div className="mb-1 text-[11px] text-zinc-500">{field.label}</div>
              <input
                type="number"
                min={field.min}
                max={field.max}
                step={field.step}
                className="w-full rounded border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-900 outline-none transition-colors focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                value={numberValue(value, field.key === "topK" ? 5 : field.key === "maxChars" ? 4000 : 0.12)}
                onChange={(e) => updateArg(props.args, props.setArgs, field.key, Number(e.target.value || 0))}
              />
            </label>
          );
        }

        if (component === "scope-select") {
          return (
            <label key={field.key} className="block">
              <div className="mb-1 text-[11px] text-zinc-500">{field.label}</div>
              <select
                className="w-full rounded border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-900 outline-none transition-colors focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                value={textValue(value)}
                onChange={(e) => updateArg(props.args, props.setArgs, field.key, e.target.value)}
              >
                <option value="">{field.placeholder || "All"}</option>
                {props.context.ragScopes.map((scope) => (
                  <option key={`${props.tool.id}-${scope}`} value={scope}>
                    {scope}
                  </option>
                ))}
              </select>
            </label>
          );
        }

        if (component === "select") {
          return (
            <label key={field.key} className="block">
              <div className="mb-1 text-[11px] text-zinc-500">{field.label}</div>
              <select
                className="w-full rounded border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-900 outline-none transition-colors focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                value={textValue(value)}
                onChange={(e) => updateArg(props.args, props.setArgs, field.key, e.target.value)}
              >
                {(field.options ?? []).map((option) => (
                  <option key={`${field.key}-${option.value}`} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          );
        }

        return (
          <label key={field.key} className="block">
            <div className="mb-1 text-[11px] text-zinc-500">{field.label}</div>
            <input
              className="w-full rounded border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-900 outline-none transition-colors focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
              value={textValue(value, field.key === "tenantId" ? props.context.tenantId : "")}
              placeholder={field.placeholder || ""}
              onChange={(e) => updateArg(props.args, props.setArgs, field.key, e.target.value)}
            />
          </label>
        );
      })}
    </div>
  );
}

function RagRetrievalPlugin(props: ToolPluginProps) {
  const normalizedArgs = {
    tenantId: textValue(props.args.tenantId, props.context.tenantId),
    query: textValue(props.args.query),
    scope: textValue(props.args.scope),
    topK: numberValue(props.args.topK, 5),
    minScore: numberValue(props.args.minScore, 0.12),
  };

  return (
    <div className="mt-3 rounded border border-zinc-300 bg-zinc-50 p-3 dark:border-zinc-700 dark:bg-zinc-900/60">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">RAG Tool UI</div>
        <AppButton type="button" size="xs" variant="info" onClick={props.context.onOpenRagViewer}>
          Open RAG Viewer
        </AppButton>
      </div>
      <GenericToolFields
        {...props}
        args={normalizedArgs}
        setArgs={(nextArgs) =>
          props.setArgs({
            tenantId: textValue(nextArgs.tenantId, props.context.tenantId),
            query: textValue(nextArgs.query),
            ...(textValue(nextArgs.scope) ? { scope: textValue(nextArgs.scope) } : {}),
            topK: numberValue(nextArgs.topK, 5),
            minScore: numberValue(nextArgs.minScore, 0.12),
          })
        }
      />
    </div>
  );
}

function WeatherResultRenderer(props: ToolResultRendererProps) {
  const result = objectValue(props.response?.result);
  const location = objectValue(result.location);
  const current = objectValue(result.current);
  const daily = objectValue(result.daily);

  if (!Object.keys(result).length) return null;

  return (
    <div className="space-y-3">
      <div className="rounded border border-zinc-200 dark:border-zinc-700 p-3">
        <div className="text-xs text-zinc-500">Location</div>
        <div className="mt-1 text-sm font-medium">
          {textValue(location.name) || textValue(location.query)}{textValue(location.country) ? `, ${textValue(location.country)}` : ""}
        </div>
        <div className="mt-1 text-xs text-zinc-500">{textValue(location.timezone)}</div>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <div className="rounded border border-zinc-200 dark:border-zinc-700 p-3">
          <div className="text-[11px] text-zinc-500">Current</div>
          <div className="mt-1 text-lg font-semibold">
            {String(current.temperature ?? "--")} {textValue(current.temperatureUnit)}
          </div>
        </div>
        <div className="rounded border border-zinc-200 dark:border-zinc-700 p-3">
          <div className="text-[11px] text-zinc-500">Max</div>
          <div className="mt-1 text-lg font-semibold">{String(daily.temperatureMax ?? "--")}</div>
        </div>
        <div className="rounded border border-zinc-200 dark:border-zinc-700 p-3">
          <div className="text-[11px] text-zinc-500">Min</div>
          <div className="mt-1 text-lg font-semibold">{String(daily.temperatureMin ?? "--")}</div>
        </div>
      </div>
    </div>
  );
}

function WebFetchResultRenderer(props: ToolResultRendererProps) {
  const result = objectValue(props.response?.result);
  if (!Object.keys(result).length) return null;

  return (
    <div className="space-y-3">
      <div className="rounded border border-zinc-200 dark:border-zinc-700 p-3">
        <div className="text-sm font-medium">{textValue(result.title) || textValue(result.url)}</div>
        <div className="mt-1 text-[11px] text-zinc-500">{textValue(result.finalUrl)}</div>
        <div className="mt-1 text-[11px] text-zinc-500">
          status {String(result.statusCode ?? "")} | {textValue(result.contentType)}
        </div>
      </div>
      <div className="rounded border border-zinc-200 dark:border-zinc-700 p-3">
        <div className="text-xs text-zinc-500 mb-1">Content Preview</div>
        <pre className="text-[11px] whitespace-pre-wrap break-words">{textValue(result.content)}</pre>
      </div>
    </div>
  );
}

function RetrievalResultRenderer(props: ToolResultRendererProps) {
  const result = objectValue(props.response?.result);
  const hits = Array.isArray(result.hits) ? result.hits : [];

  return (
    <div className="space-y-3">
      <div className="rounded border border-zinc-200 dark:border-zinc-700 p-3">
        <div className="text-xs text-zinc-500">
          {textValue(result.query)} {textValue(result.scope) ? `| scope: ${textValue(result.scope)}` : "| all scopes"}
        </div>
        <div className="mt-1 text-sm font-medium">{hits.length} hits</div>
      </div>
      {hits.map((hit, index) => {
        const item = objectValue(hit);
        return (
          <div key={`${textValue(item.documentId)}-${index}`} className="rounded border border-zinc-200 dark:border-zinc-700 p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm font-medium">{textValue(item.title) || textValue(item.documentId)}</div>
              <div className="text-[11px] text-zinc-500">score {String(item.score ?? "")}</div>
            </div>
            <div className="mt-1 text-[11px] text-zinc-500">
              {textValue(item.scope)} {textValue(item.source) ? `| ${textValue(item.source)}` : ""}
            </div>
            <pre className="mt-2 text-[11px] whitespace-pre-wrap break-words">{textValue(item.content)}</pre>
          </div>
        );
      })}
      {!hits.length ? <div className="text-xs text-zinc-500">No hits.</div> : null}
    </div>
  );
}

const pluginRegistry: Record<string, (props: ToolPluginProps) => ReactNode> = {
  "rag-retrieval": RagRetrievalPlugin,
};

const resultRendererRegistry: Record<string, (props: ToolResultRendererProps) => ReactNode> = {
  retrieval: RetrievalResultRenderer,
  weather: WeatherResultRenderer,
  "web-fetch": WebFetchResultRenderer,
};

export function parseToolArgs(value: string) {
  try {
    const parsed = JSON.parse(value || "{}");
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

export function ToolPluginHost(props: ToolPluginProps) {
  const Plugin = props.tool.uiPlugin ? pluginRegistry[props.tool.uiPlugin] : undefined;
  if (Plugin) {
    return <Plugin {...props} />;
  }
  if (props.tool.uiSchema?.fields?.length) {
    return <GenericToolFields {...props} />;
  }
  return null;
}

export function ToolResultRenderer(props: ToolResultRendererProps) {
  const Renderer = resultRendererRegistry[props.tool.id];
  if (Renderer) {
    return <Renderer {...props} />;
  }
  return null;
}
