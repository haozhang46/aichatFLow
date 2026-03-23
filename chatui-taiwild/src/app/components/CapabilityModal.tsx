"use client";

import * as yup from "yup";

import AppButton from "@/components/ui/AppButton";
import BaseForm, { BaseField } from "@/components/ui/BaseForm";
import AppModal from "@/components/ui/AppModal";
import type { CapabilityAgent, CapabilitySkill, CapabilityTool } from "@/app/components/modalTypes";

type Props = {
  open: boolean;
  onClose: () => void;
  capabilityTab: "existing" | "add";
  setCapabilityTab: (tab: "existing" | "add") => void;
  capabilityQuery: string;
  setCapabilityQuery: (value: string) => void;
  loadCapabilities: (keyword?: string, page?: number) => Promise<void>;
  capabilityAgents: CapabilityAgent[];
  capabilitySkills: CapabilitySkill[];
  capabilityTools: CapabilityTool[];
  capabilityLoading: boolean;
  capabilityInstallingSkillId: string | null;
  capabilityTogglingWhitelistSkillId: string | null;
  capabilityTogglingToolPolicyKey: string | null;
  installSkill: (skillId: string) => Promise<void>;
  toggleWhitelist: (skillId: string, enabled: boolean) => Promise<void>;
  toggleToolPolicy: (toolId: string, field: "allowlisted" | "denylisted", enabled: boolean) => Promise<void>;
  openAgentPlayground: (agentId: string) => void;
  openToolPlayground: (toolId: string) => void;
  capabilityPage: number;
  capabilitySkillsTotal: number;
  capabilityPageSize: number;
  onlineQuery: string;
  setOnlineQuery: (value: string) => void;
  onlineSkillsLoading: boolean;
  searchOnlineSkills: () => Promise<void>;
  onlineSkills: CapabilitySkill[];
  onlineAddingSkillId: string | null;
  addOnlineSkill: (skillId: string) => Promise<void>;
  customAgentCreating: boolean;
  createCustomAgent: (payload: { agentId: string; label: string; description: string }) => Promise<void>;
  customAgents: CapabilityAgent[];
  customAgentDeletingId: string | null;
  deleteCustomAgent: (agentId: string) => Promise<void>;
  personalSkillRootPath: string;
  personalSkillPathInput: string;
  personalSkillPathSaving: boolean;
  savePersonalSkillPath: (path: string) => Promise<void>;
  personalSkillTreeLoading: boolean;
  loadPersonalSkillTree: () => Promise<void>;
  pickPersonalSkillPath: () => string | Promise<string>;
  personalSkillItems: Array<{ type: "dir" | "md"; path: string }>;
};

const createAgentSchema = yup.object({
  agentId: yup.string().trim().required("请输入 agent id"),
  label: yup.string().trim().required("请输入 label"),
  description: yup.string().trim().default(""),
});

const personalSkillPathSchema = yup.object({
  path: yup.string().trim().required("请输入技能树目录"),
});

export default function CapabilityModal(props: Props) {
  if (!props.open) return null;
  return (
    <AppModal panelClassName="w-full max-w-4xl h-[76vh] bg-white dark:bg-zinc-900 rounded border border-zinc-300 dark:border-zinc-700 flex flex-col">
      <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-700 flex items-center gap-2">
        <div className="font-medium flex-1">可用 Agent / Skill</div>
        <div className="flex items-center gap-1 border border-zinc-300 dark:border-zinc-700 rounded p-0.5">
          <AppButton
            type="button"
            size="xs"
            variant="tab"
            className={props.capabilityTab === "existing" ? "bg-zinc-200 dark:bg-zinc-700" : ""}
            onClick={() => props.setCapabilityTab("existing")}
          >
            已有列表
          </AppButton>
          <AppButton
            type="button"
            size="xs"
            variant="tab"
            className={props.capabilityTab === "add" ? "bg-zinc-200 dark:bg-zinc-700" : ""}
            onClick={() => props.setCapabilityTab("add")}
          >
            添加
          </AppButton>
        </div>
        {props.capabilityTab === "existing" ? (
          <>
            <input
              className="border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-sm"
              placeholder="search agent/skill..."
              value={props.capabilityQuery}
              onChange={(e) => props.setCapabilityQuery(e.target.value)}
            />
            <AppButton type="button" size="xs" loading={props.capabilityLoading} loadingText="Searching..." onClick={() => void props.loadCapabilities(props.capabilityQuery, 1)}>
              Search
            </AppButton>
          </>
        ) : null}
        <AppButton type="button" onClick={props.onClose}>
          关闭
        </AppButton>
      </div>
      {props.capabilityTab === "existing" ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 overflow-auto">
          <div>
            <div className="text-sm font-medium mb-2">Agents</div>
            <div className="space-y-2">
              {props.capabilityAgents.map((a) => (
                <div key={a.id} className="border border-zinc-200 dark:border-zinc-700 rounded p-2">
                  <div className="text-sm font-medium">{a.label}</div>
                  <div className="text-xs text-zinc-500">{a.description}</div>
                  <div className="mt-2">
                    <AppButton type="button" size="xs" variant="info" onClick={() => props.openAgentPlayground(a.id)}>
                      Playground
                    </AppButton>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="text-sm font-medium mb-2">Tools</div>
            <div className="space-y-2">
              {props.capabilityTools.map((tool) => (
                <div key={tool.id} className="border border-zinc-200 dark:border-zinc-700 rounded p-2">
                  <div className="text-sm font-medium">{tool.name}</div>
                  <div className="text-xs text-zinc-500">{tool.id}</div>
                  <div className="text-xs text-zinc-500 mt-1">{tool.description || "No description"}</div>
                  <div className="text-xs text-zinc-500 mt-1">
                    {tool.category || "general"} | {tool.builtin ? "builtin" : "external"}
                  </div>
                  <div className="mt-2 flex items-center gap-2">
                    <label className="text-xs flex items-center gap-1">
                      <input
                        type="checkbox"
                        checked={Boolean(tool.allowlisted)}
                        disabled={props.capabilityTogglingToolPolicyKey === `${tool.id}:allowlisted`}
                        onChange={(e) => void props.toggleToolPolicy(tool.id, "allowlisted", e.target.checked)}
                      />
                      allowlist
                    </label>
                    <label className="text-xs flex items-center gap-1">
                      <input
                        type="checkbox"
                        checked={Boolean(tool.denylisted)}
                        disabled={props.capabilityTogglingToolPolicyKey === `${tool.id}:denylisted`}
                        onChange={(e) => void props.toggleToolPolicy(tool.id, "denylisted", e.target.checked)}
                      />
                      denylist
                    </label>
                    <AppButton type="button" size="xs" variant="info" onClick={() => props.openToolPlayground(tool.id)}>
                      Playground
                    </AppButton>
                  </div>
                </div>
              ))}
              {props.capabilityTools.length === 0 ? (
                <div className="text-xs text-zinc-500">暂无 tools。</div>
              ) : null}
            </div>
          </div>
          <div>
            <div className="text-sm font-medium mb-2">Skills</div>
            <div className="space-y-2">
              {props.capabilitySkills.map((s) => (
                <div key={s.id} className="border border-zinc-200 dark:border-zinc-700 rounded p-2">
                  <div className="text-sm font-medium">{s.name}</div>
                  <div className="text-xs text-zinc-500">
                    {s.source} | {s.installed ? "installed" : "not installed"}
                  </div>
                  <div className="mt-2 flex items-center gap-2">
                    <AppButton
                      type="button"
                      size="xs"
                      loading={props.capabilityInstallingSkillId === s.id}
                      loadingText="安装中..."
                      onClick={() => void props.installSkill(s.id)}
                      disabled={s.installed}
                    >
                      下载/安装
                    </AppButton>
                    <label className="text-xs flex items-center gap-1">
                      <input
                        type="checkbox"
                        checked={Boolean(s.whitelisted)}
                        disabled={props.capabilityTogglingWhitelistSkillId === s.id}
                        onChange={(e) => void props.toggleWhitelist(s.id, e.target.checked)}
                      />
                      whitelist
                    </label>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-3 flex items-center justify-between text-xs text-zinc-500">
              <div>
                page {props.capabilityPage} / {Math.max(1, Math.ceil(props.capabilitySkillsTotal / props.capabilityPageSize))}
              </div>
              <div className="flex items-center gap-2">
                <AppButton
                  type="button"
                  size="xs"
                  loading={props.capabilityLoading}
                  loadingText="Loading..."
                  disabled={props.capabilityPage <= 1}
                  onClick={() => void props.loadCapabilities(props.capabilityQuery, props.capabilityPage - 1)}
                >
                  Prev
                </AppButton>
                <AppButton
                  type="button"
                  size="xs"
                  loading={props.capabilityLoading}
                  loadingText="Loading..."
                  disabled={props.capabilityPage * props.capabilityPageSize >= props.capabilitySkillsTotal}
                  onClick={() => void props.loadCapabilities(props.capabilityQuery, props.capabilityPage + 1)}
                >
                  Next
                </AppButton>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="p-4 overflow-auto">
          <div className="text-xs text-zinc-500 mb-2">
            ClawHub（OpenClaw 公共 skill 注册表，向量检索）— 由后端代理{" "}
            <code className="text-[10px]">GET /v1/clawhub/search</code>，只读搜索无需 API Key；本机安装请使用官方{" "}
            <code className="text-[10px]">clawhub install &lt;slug&gt;</code>。
          </div>
          <div className="flex items-center gap-2 mb-3">
            <input
              className="border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-sm flex-1"
              placeholder="搜索 ClawHub skills（自然语言）..."
              value={props.onlineQuery}
              onChange={(e) => props.setOnlineQuery(e.target.value)}
            />
            <AppButton type="button" size="xs" loading={props.onlineSkillsLoading} loadingText="Searching..." onClick={() => void props.searchOnlineSkills()}>
              Search ClawHub
            </AppButton>
          </div>
          <div className="space-y-2">
            {props.onlineSkills.map((s) => (
              <div key={s.id} className="border border-zinc-200 dark:border-zinc-700 rounded p-2">
                <div className="text-sm font-medium">{s.name}</div>
                <div className="text-xs text-zinc-600 dark:text-zinc-400 font-mono">{s.id}</div>
                {s.summary ? <div className="text-xs text-zinc-500 mt-1 line-clamp-3">{s.summary}</div> : null}
                <div className="text-xs text-zinc-500">
                  {s.source} | {s.installed ? "installed" : "not installed"}
                  {typeof s.score === "number" ? ` | score ${s.score.toFixed(2)}` : ""}
                </div>
                <div className="mt-2 flex items-center gap-2">
                  <AppButton
                    type="button"
                    size="xs"
                    loading={props.onlineAddingSkillId === s.id}
                    loadingText="Adding..."
                    onClick={() => void props.addOnlineSkill(s.id)}
                  >
                    加入已有列表
                  </AppButton>
                </div>
              </div>
            ))}
            {props.onlineSkills.length === 0 ? (
              <div className="text-xs text-zinc-500">输入关键词后搜索 ClawHub（需本机可访问 clawhub.ai）。</div>
            ) : null}
          </div>
          <div className="mt-6 border-t border-zinc-200 dark:border-zinc-700 pt-4">
            <div className="text-sm font-medium mb-2">自建 Agent 注册中心</div>
            <BaseForm
              initialValues={{ agentId: "", label: "", description: "" }}
              validationSchema={createAgentSchema}
              onSubmit={async (values, helpers) => {
                await props.createCustomAgent({
                  agentId: values.agentId.trim(),
                  label: values.label.trim(),
                  description: values.description.trim(),
                });
                helpers.resetForm();
              }}
              className="space-y-2"
            >
              {({ isSubmitting, isValid }) => (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                    <BaseField name="agentId" placeholder="agent id" />
                    <BaseField name="label" placeholder="label" />
                    <BaseField name="description" placeholder="description" />
                  </div>
                  <AppButton type="submit" size="xs" loading={isSubmitting || props.customAgentCreating} loadingText="创建中..." disabled={!isValid}>
                    添加自建 Agent
                  </AppButton>
                </>
              )}
            </BaseForm>
            <div className="mt-3 space-y-2">
              {props.customAgents.map((a) => (
                <div key={a.id} className="border border-zinc-200 dark:border-zinc-700 rounded p-2">
                  <div className="text-sm font-medium">{a.label}</div>
                  <div className="text-xs text-zinc-500">{a.id}</div>
                  <div className="text-xs text-zinc-500">{a.description}</div>
                  <div className="mt-1 flex items-center gap-2">
                    <AppButton type="button" size="xs" variant="info" onClick={() => props.openAgentPlayground(a.id)}>
                      Playground
                    </AppButton>
                    <AppButton
                      type="button"
                      size="xs"
                      variant="danger"
                      loading={props.customAgentDeletingId === a.id}
                      loadingText="删除中..."
                      onClick={() => void props.deleteCustomAgent(a.id)}
                    >
                      删除
                    </AppButton>
                  </div>
                </div>
              ))}
              {props.customAgents.length === 0 ? <div className="text-xs text-zinc-500">暂无自建 agent。</div> : null}
            </div>
          </div>
          <div className="mt-6 border-t border-zinc-200 dark:border-zinc-700 pt-4">
            <div className="text-sm font-medium mb-2">个人能力技能树（本地 Markdown）</div>
            <div className="text-xs text-zinc-500 mb-2">当前路径: {props.personalSkillRootPath || "-"}</div>
            <BaseForm
              initialValues={{ path: props.personalSkillPathInput }}
              validationSchema={personalSkillPathSchema}
              onSubmit={async (values) => {
                await props.savePersonalSkillPath(values.path.trim());
              }}
              enableReinitialize
              className="mb-2"
            >
              {({ isSubmitting, isValid, setFieldValue }) => (
                <div className="flex items-start gap-2">
                  <BaseField
                    name="path"
                    className="flex-1"
                    placeholder="/Users/you/personal-skills"
                  />
                  <AppButton
                    type="button"
                    size="xs"
                    onClick={async () => {
                      const result = await props.pickPersonalSkillPath();
                      if (typeof result === "string" && result.trim()) {
                        setFieldValue("path", result);
                      }
                    }}
                  >
                    选择路径
                  </AppButton>
                  <AppButton type="submit" size="xs" variant="info" loading={isSubmitting || props.personalSkillPathSaving} loadingText="保存中..." disabled={!isValid}>
                    保存路径
                  </AppButton>
                  <AppButton type="button" size="xs" loading={props.personalSkillTreeLoading} loadingText="刷新中..." onClick={() => void props.loadPersonalSkillTree()}>
                    刷新
                  </AppButton>
                </div>
              )}
            </BaseForm>
            <div className="max-h-36 overflow-auto border border-zinc-200 dark:border-zinc-700 rounded p-2 space-y-1">
              {props.personalSkillItems.length === 0 ? (
                <div className="text-xs text-zinc-500">暂无 md 文件，往该目录添加 Markdown 即可。</div>
              ) : (
                props.personalSkillItems.map((item) => (
                  <div key={`${item.type}-${item.path}`} className="text-xs text-zinc-600 dark:text-zinc-300">
                    {item.type === "dir" ? "📁" : "📄"} {item.path}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </AppModal>
  );
}
