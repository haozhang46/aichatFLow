"use client";

import AppButton from "@/components/ui/AppButton";
import AppModal from "@/components/ui/AppModal";
import type { DeepSeekConfig } from "@/app/components/modalTypes";

type Props = {
  open: boolean;
  onClose: () => void;
  deepseekConfig: DeepSeekConfig;
  setDeepseekConfig: (updater: (prev: DeepSeekConfig) => DeepSeekConfig) => void;
};

export default function DeepseekModal(props: Props) {
  if (!props.open) return null;
  return (
    <AppModal panelClassName="w-full max-w-xl bg-white dark:bg-zinc-900 rounded border border-zinc-300 dark:border-zinc-700 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <div className="font-medium flex-1">DeepSeek 配置</div>
        <AppButton type="button" onClick={props.onClose}>
          关闭
        </AppButton>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={props.deepseekConfig.enabled}
          onChange={(e) => props.setDeepseekConfig((prev) => ({ ...prev, enabled: e.target.checked }))}
        />
        启用 DeepSeek（本地保存）
      </label>
      <label className="block">
        <div className="text-xs text-zinc-500 mb-1">API Key</div>
        <input
          type="password"
          className="w-full border border-zinc-300 dark:border-zinc-700 rounded px-3 py-2 bg-white dark:bg-zinc-900"
          value={props.deepseekConfig.apiKey}
          onChange={(e) => props.setDeepseekConfig((prev) => ({ ...prev, apiKey: e.target.value }))}
          placeholder="sk-..."
        />
      </label>
      <label className="block">
        <div className="text-xs text-zinc-500 mb-1">Base URL</div>
        <input
          className="w-full border border-zinc-300 dark:border-zinc-700 rounded px-3 py-2 bg-white dark:bg-zinc-900"
          value={props.deepseekConfig.baseUrl}
          onChange={(e) => props.setDeepseekConfig((prev) => ({ ...prev, baseUrl: e.target.value }))}
          placeholder="https://api.deepseek.com/v1"
        />
      </label>
      <label className="block">
        <div className="text-xs text-zinc-500 mb-1">Model</div>
        <input
          className="w-full border border-zinc-300 dark:border-zinc-700 rounded px-3 py-2 bg-white dark:bg-zinc-900"
          value={props.deepseekConfig.model}
          onChange={(e) => props.setDeepseekConfig((prev) => ({ ...prev, model: e.target.value }))}
          placeholder="deepseek-chat"
        />
      </label>
      <div className="text-xs text-zinc-500">配置会随浏览器本地保存；发送 plan/execute 时会附带 llmConfig 参数。</div>
    </AppModal>
  );
}
