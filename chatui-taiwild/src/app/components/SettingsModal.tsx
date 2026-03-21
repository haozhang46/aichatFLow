"use client";

import AppButton from "@/components/ui/AppButton";
import AppModal from "@/components/ui/AppModal";
import type { RagConfig, Strategy } from "@/app/components/modalTypes";

type Props = {
  open: boolean;
  onClose: () => void;
  tenantId: string;
  strategy: Strategy;
  setTenantId: (value: string) => void;
  setStrategy: (value: Strategy) => void;
  ragConfig: RagConfig;
  setRagConfig: (updater: (prev: RagConfig) => RagConfig) => void;
  apiBaseUrl: string;
};

export default function SettingsModal(props: Props) {
  if (!props.open) return null;

  return (
    <AppModal panelClassName="w-full max-w-xl bg-white dark:bg-zinc-900 rounded border border-zinc-300 dark:border-zinc-700 p-4 space-y-4">
      <div className="flex items-center gap-2">
        <div className="font-medium flex-1">Settings</div>
        <AppButton type="button" onClick={props.onClose}>
          关闭
        </AppButton>
      </div>

      <label className="block">
        <div className="text-xs text-zinc-500 mb-1">tenantId</div>
        <input
          className="w-full border border-zinc-300 dark:border-zinc-700 rounded px-3 py-2 bg-white dark:bg-zinc-900"
          value={props.tenantId}
          onChange={(e) => props.setTenantId(e.target.value)}
          placeholder="tenant-a"
        />
      </label>

      <label className="block">
        <div className="text-xs text-zinc-500 mb-1">strategy</div>
        <select
          className="w-full border border-zinc-300 dark:border-zinc-700 rounded px-3 py-2 bg-white dark:bg-zinc-900"
          value={props.strategy}
          onChange={(e) => props.setStrategy(e.target.value as Strategy)}
        >
          <option value="auto">auto</option>
          <option value="agent">agent</option>
          <option value="react">react</option>
          <option value="workflow">workflow</option>
        </select>
      </label>

      <div className="rounded border border-zinc-200 dark:border-zinc-700 px-3 py-3 space-y-3">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={props.ragConfig.enabled}
            onChange={(e) => props.setRagConfig((prev) => ({ ...prev, enabled: e.target.checked }))}
          />
          启用 RAG
        </label>

        <label className="block">
          <div className="text-xs text-zinc-500 mb-1">RAG Scope</div>
          <input
            className="w-full border border-zinc-300 dark:border-zinc-700 rounded px-3 py-2 bg-white dark:bg-zinc-900"
            value={props.ragConfig.scope}
            onChange={(e) => props.setRagConfig((prev) => ({ ...prev, scope: e.target.value }))}
            placeholder="refund-policy"
          />
        </label>

        <label className="block">
          <div className="text-xs text-zinc-500 mb-1">RAG TopK</div>
          <input
            type="number"
            min={1}
            max={20}
            className="w-full border border-zinc-300 dark:border-zinc-700 rounded px-3 py-2 bg-white dark:bg-zinc-900"
            value={props.ragConfig.topK}
            onChange={(e) =>
              props.setRagConfig((prev) => ({
                ...prev,
                topK: Number.isFinite(Number(e.target.value)) ? Math.max(1, Number(e.target.value)) : prev.topK,
              }))
            }
          />
        </label>
      </div>

      <div className="rounded border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-950 px-3 py-2 text-xs text-zinc-500">
        API: <span className="font-mono">{props.apiBaseUrl}</span>
      </div>
    </AppModal>
  );
}
