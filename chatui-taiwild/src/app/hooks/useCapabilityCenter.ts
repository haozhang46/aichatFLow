"use client";

import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import type { CapabilityAgent, CapabilitySkill, CapabilityTool } from "@/app/components/modalTypes";
import type { ChatMessage } from "@/app/hooks/useChatController";
import { apiDelete, apiGet, apiPost } from "@/lib/api-client";
import { useApiSWR } from "@/lib/swr";

type Params = {
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>;
  setInput: Dispatch<SetStateAction<string>>;
  setError: Dispatch<SetStateAction<string | null>>;
};

function appendAssistantMessage(
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>,
  content: string
) {
  setMessages((prev) => [...prev, { role: "assistant", content }]);
}

export function useCapabilityCenter({ setMessages, setInput, setError }: Params) {
  const [capabilityTab, setCapabilityTab] = useState<"existing" | "add">("existing");
  const [capabilityQuery, setCapabilityQuery] = useState("");
  const [capabilityInstallingSkillId, setCapabilityInstallingSkillId] = useState<string | null>(null);
  const [capabilityTogglingWhitelistSkillId, setCapabilityTogglingWhitelistSkillId] = useState<string | null>(null);
  const [capabilityTogglingToolPolicyKey, setCapabilityTogglingToolPolicyKey] = useState<string | null>(null);
  const [personalSkillPathInput, setPersonalSkillPathInput] = useState("");
  const [personalSkillPathSaving, setPersonalSkillPathSaving] = useState(false);
  const [capabilityPage, setCapabilityPage] = useState(1);
  const capabilityPageSize = 8;
  const [onlineQuery, setOnlineQuery] = useState("");
  const [onlineSkills, setOnlineSkills] = useState<CapabilitySkill[]>([]);
  const [onlineSkillsLoading, setOnlineSkillsLoading] = useState(false);
  const [onlineAddingSkillId, setOnlineAddingSkillId] = useState<string | null>(null);
  const [customAgentCreating, setCustomAgentCreating] = useState(false);
  const [customAgentDeletingId, setCustomAgentDeletingId] = useState<string | null>(null);

  const capabilitiesSWR = useApiSWR<{
    agents?: CapabilityAgent[];
    skills?: CapabilitySkill[];
    tools?: CapabilityTool[];
    whitelist?: string[];
    skillsTotal?: number;
    page?: number;
  }>("/v1/capabilities", {
    q: capabilityQuery || undefined,
    page: capabilityPage,
    pageSize: capabilityPageSize,
  });
  const personalSkillTreeSWR = useApiSWR<{ rootPath?: string; items?: Array<{ type?: string; path?: string }> }>(
    "/v1/personal-skills/tree"
  );
  const customAgentsSWR = useApiSWR<{ items?: CapabilityAgent[] }>("/v1/agents");

  const capabilityAgents = Array.isArray(capabilitiesSWR.data?.agents) ? capabilitiesSWR.data.agents : [];
  const capabilitySkills = Array.isArray(capabilitiesSWR.data?.skills) ? capabilitiesSWR.data.skills : [];
  const capabilityTools = Array.isArray(capabilitiesSWR.data?.tools) ? capabilitiesSWR.data.tools : [];
  const capabilityWhitelist = Array.isArray(capabilitiesSWR.data?.whitelist)
    ? capabilitiesSWR.data.whitelist.map((x: unknown) => String(x))
    : [];
  const capabilitySkillsTotal = Number(capabilitiesSWR.data?.skillsTotal ?? 0);
  const capabilityLoading = capabilitiesSWR.isLoading || capabilitiesSWR.isValidating;

  const personalSkillRootPath =
    typeof personalSkillTreeSWR.data?.rootPath === "string" ? personalSkillTreeSWR.data.rootPath : "";
  const personalSkillItems = Array.isArray(personalSkillTreeSWR.data?.items)
    ? personalSkillTreeSWR.data.items
        .map((item) => ({
          type: item?.type === "dir" ? "dir" : ("md" as "dir" | "md"),
          path: String(item?.path ?? ""),
        }))
        .filter((item) => item.path.length > 0)
    : [];
  const personalSkillTreeLoading = personalSkillTreeSWR.isLoading || personalSkillTreeSWR.isValidating;
  const customAgents = Array.isArray(customAgentsSWR.data?.items) ? customAgentsSWR.data.items : [];

  useEffect(() => {
    if (!personalSkillRootPath) return;
    setPersonalSkillPathInput((prev) => (prev.trim().length > 0 ? prev : personalSkillRootPath));
  }, [personalSkillRootPath]);

  async function loadCapabilities(keyword = "", page = 1) {
    setCapabilityQuery(keyword);
    setCapabilityPage(page);
    if (keyword === capabilityQuery && page === capabilityPage) {
      await capabilitiesSWR.mutate();
    }
  }

  async function loadPersonalSkillTree() {
    await personalSkillTreeSWR.mutate();
  }

  async function savePersonalSkillPath(pathInput: string) {
    const path = pathInput.trim();
    if (!path) return;
    setPersonalSkillPathSaving(true);
    try {
      const data = await apiPost<{ rootPath?: string; items?: Array<{ type?: "dir" | "md"; path?: string }> }>(
        "/v1/personal-skills/path",
        { path }
      );
      setPersonalSkillPathInput(path);
      await personalSkillTreeSWR.mutate(data, false);
      appendAssistantMessage(setMessages, "个人技能树路径已更新。");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPersonalSkillPathSaving(false);
    }
  }

  async function pickPersonalSkillPath() {
    const picker = (window as Window & { showDirectoryPicker?: () => Promise<{ name?: string }> }).showDirectoryPicker;
    if (!picker) return "";
    try {
      const handle = await picker();
      if (handle?.name) {
        setPersonalSkillPathInput(handle.name);
        return handle.name;
      }
    } catch {
      // User canceled directory picker.
    }
    return "";
  }

  async function installSkill(skillId: string) {
    setCapabilityInstallingSkillId(skillId);
    try {
      const data = await apiPost<{ message?: string }>("/v1/capabilities/install", { skillId });
      appendAssistantMessage(setMessages, data?.message ?? "安装成功");
      await capabilitiesSWR.mutate();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setCapabilityInstallingSkillId(null);
    }
  }

  async function toggleWhitelist(skillId: string, enabled: boolean) {
    setCapabilityTogglingWhitelistSkillId(skillId);
    try {
      const data = await apiPost<{ skillId?: string; enabled?: boolean }>("/v1/capabilities/whitelist", {
        skillId,
        enabled,
      });
      appendAssistantMessage(setMessages, `Whitelist updated: ${data?.skillId} -> ${data?.enabled}`);
      await capabilitiesSWR.mutate();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setCapabilityTogglingWhitelistSkillId(null);
    }
  }

  async function toggleToolPolicy(toolId: string, field: "allowlisted" | "denylisted", enabled: boolean) {
    const actionKey = `${toolId}:${field}`;
    setCapabilityTogglingToolPolicyKey(actionKey);
    try {
      await apiPost("/v1/capabilities/tools/policy", { toolId, [field]: enabled });
      await capabilitiesSWR.mutate();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setCapabilityTogglingToolPolicyKey(null);
    }
  }

  async function searchOnlineSkills() {
    setOnlineSkillsLoading(true);
    try {
      const data = await apiGet<{ items?: CapabilitySkill[] }>("/v1/clawhub/search", {
        q: onlineQuery,
        limit: 25,
      });
      setOnlineSkills(Array.isArray(data?.items) ? data.items : []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setOnlineSkillsLoading(false);
    }
  }

  async function addOnlineSkill(skillId: string) {
    setOnlineAddingSkillId(skillId);
    try {
      const data = await apiPost<{ message?: string }>("/v1/clawhub/register", { slug: skillId });
      appendAssistantMessage(setMessages, data?.message ?? "已加入列表");
      await loadCapabilities(capabilityQuery, 1);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setOnlineAddingSkillId(null);
    }
  }

  async function createCustomAgent(payload: { agentId: string; label: string; description: string }) {
    setCustomAgentCreating(true);
    try {
      const data = await apiPost<{ agent?: { id?: string; label?: string; description?: string } }>("/v1/agents", {
        agentId: payload.agentId,
        label: payload.label,
        description: payload.description,
      });
      const created = data?.agent;
      const createdId = created?.id ?? payload.agentId;
      const createdLabel = created?.label ?? payload.label ?? createdId;
      const createdDesc = created?.description ?? payload.description ?? "";
      await customAgentsSWR.mutate();
      await loadCapabilities(capabilityQuery, capabilityPage);
      appendAssistantMessage(
        setMessages,
        `已创建自建 Agent: ${createdLabel} (${createdId})\n` +
          (createdDesc ? `描述: ${createdDesc}\n` : "") +
          "初始 Plan:\n" +
          "1. 识别并澄清用户目标\n" +
          "2. 生成可执行步骤与所需 skill\n" +
          "3. 等待用户确认后执行\n\n" +
          "请继续输入你的意图（例如：帮我规划今天上海出行）。"
      );
      setInput("");
      return { createdId, createdLabel, createdDesc };
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    } finally {
      setCustomAgentCreating(false);
    }
  }

  async function deleteCustomAgent(agentId: string) {
    setCustomAgentDeletingId(agentId);
    try {
      const data = await apiDelete<{ status?: string }>(`/v1/agents/${encodeURIComponent(agentId)}`);
      if (data?.status === "success") {
        await customAgentsSWR.mutate();
        await loadCapabilities(capabilityQuery, capabilityPage);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setCustomAgentDeletingId(null);
    }
  }

  async function refreshCustomAgents() {
    await customAgentsSWR.mutate();
  }

  return {
    capabilityTab,
    setCapabilityTab,
    capabilityQuery,
    setCapabilityQuery,
    loadCapabilities,
    capabilityAgents,
    capabilitySkills,
    capabilityTools,
    capabilityLoading,
    capabilityInstallingSkillId,
    capabilityTogglingWhitelistSkillId,
    capabilityTogglingToolPolicyKey,
    installSkill,
    toggleWhitelist,
    toggleToolPolicy,
    capabilityWhitelist,
    capabilityPage,
    capabilitySkillsTotal,
    capabilityPageSize,
    onlineQuery,
    setOnlineQuery,
    onlineSkillsLoading,
    searchOnlineSkills,
    onlineSkills,
    onlineAddingSkillId,
    addOnlineSkill,
    customAgentCreating,
    createCustomAgent,
    customAgents,
    refreshCustomAgents,
    customAgentDeletingId,
    deleteCustomAgent,
    personalSkillRootPath,
    personalSkillPathInput,
    personalSkillPathSaving,
    savePersonalSkillPath,
    personalSkillTreeLoading,
    loadPersonalSkillTree,
    pickPersonalSkillPath,
    personalSkillItems,
  };
}
