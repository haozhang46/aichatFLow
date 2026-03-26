"use client";

import { useState } from "react";
import {
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";

export type FlowSource = {
  title: string;
  mode: string;
  lines: string[];
  skills: string[];
};

export type FolderAuthorization = {
  path: string;
  permission: string;
};

function normalizePermission(input: string) {
  const trimmed = input.replace(/\D/g, "").slice(0, 3);
  if (!trimmed) return "777";
  return trimmed;
}

export function useTaskFlowController() {
  const [open, setOpen] = useState(false);
  const [editable, setEditable] = useState(true);
  const [title, setTitle] = useState("");
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [flowSkills, setFlowSkills] = useState<string[]>([]);
  const [flowSkillInput, setFlowSkillInput] = useState("");
  const [flowFolderAuths, setFlowFolderAuths] = useState<FolderAuthorization[]>([]);
  const [flowFolderPathInput, setFlowFolderPathInput] = useState("");
  const [flowFolderPermInput, setFlowFolderPermInput] = useState("777");

  function close() {
    setOpen(false);
  }

  function applyFlowSkills(skills: string[]) {
    const normalized = skills.filter((s) => s.trim().length > 0);
    setFlowSkills(normalized);
    setNodes((prev) =>
      prev.map((node) => {
        if (node.id === "skills-node") {
          return {
            ...node,
            data: {
              ...(node.data || {}),
              skills: normalized,
              editable,
              onAddSkill: (skill: string) => addFlowSkillByNode(skill),
              onRemoveSkill: (skill: string) => removeFlowSkill(skill),
            },
          };
        }
        const label = String(node.data?.label ?? "");
        const updatedLabel = label.replace(
          /skill:\s*.*/i,
          `skill: ${normalized.length > 0 ? normalized.join(", ") : "none"}`
        );
        return { ...node, data: { ...node.data, label: updatedLabel } };
      })
    );
  }

  function buildFlowGraph(source: FlowSource) {
    const graphNodes: Node[] = source.lines.map((line, idx) => ({
      id: `n-${idx + 1}`,
      position: { x: 80 + idx * 280, y: 120 },
      data: {
        label: `Step ${idx + 1}\n${line}\nagent: ${source.mode}\nskill: ${
          source.skills.length > 0 ? source.skills.join(", ") : "none"
        }`,
      },
      draggable: true,
      style: {
        color: "#18181b",
        background: "#f4f4f5",
        border: "1px solid #a1a1aa",
        borderRadius: "8px",
        fontSize: "12px",
        whiteSpace: "pre-wrap",
        width: 240,
      },
    }));
    const skillNode: Node = {
      id: "skills-node",
      type: "skillNode",
      position: { x: 80 + Math.max(0, source.lines.length - 1) * 280, y: 320 },
      data: {
        skills: source.skills,
        editable,
        onAddSkill: (skill: string) => addFlowSkillByNode(skill),
        onRemoveSkill: (skill: string) => removeFlowSkill(skill),
      },
      draggable: true,
    };
    const authNode: Node = {
      id: "auth-node",
      position: { x: 80, y: 420 },
      data: {
        label: "Folder Auth\nnone",
      },
      draggable: true,
      style: {
        color: "#18181b",
        background: "#fafafa",
        border: "1px solid #a1a1aa",
        borderRadius: "8px",
        fontSize: "12px",
        whiteSpace: "pre-wrap",
        width: 280,
      },
    };
    const graphEdges: Edge[] = source.lines.slice(1).map((_, idx) => ({
      id: `e-${idx + 1}-${idx + 2}`,
      source: `n-${idx + 1}`,
      target: `n-${idx + 2}`,
      animated: true,
    }));
    if (graphNodes.length > 0) {
      graphEdges.push({
        id: "e-last-skill",
        source: `n-${graphNodes.length}`,
        target: "skills-node",
        animated: true,
      });
    }
    graphEdges.push({
      id: "e-skill-auth",
      source: "skills-node",
      target: "auth-node",
      animated: true,
    });
    return { nodes: [...graphNodes, skillNode, authNode], edges: graphEdges };
  }

  function openTaskFlow(source: FlowSource, nextEditable: boolean) {
    setEditable(nextEditable);
    const graph = buildFlowGraph(source);
    setNodes(graph.nodes);
    setEdges(graph.edges);
    setTitle(source.title);
    setFlowSkills(source.skills);
    setFlowSkillInput("");
    setFlowFolderAuths([]);
    setFlowFolderPathInput("");
    setFlowFolderPermInput("777");
    setOpen(true);
  }

  function onConnect(params: Edge | Connection) {
    if (!editable) return;
    setEdges((current) => addEdge(params, current));
  }

  function addFlowSkillByNode(skill: string) {
    const next = skill.trim();
    if (!next) return;
    if (flowSkills.includes(next)) return;
    applyFlowSkills([...flowSkills, next]);
  }

  function addFlowSkill() {
    const next = flowSkillInput.trim();
    if (!next) return;
    addFlowSkillByNode(next);
    setFlowSkillInput("");
  }

  function removeFlowSkill(skill: string) {
    applyFlowSkills(flowSkills.filter((s) => s !== skill));
  }

  function applyFlowFolderAuths(next: FolderAuthorization[]) {
    setFlowFolderAuths(next);
    const label =
      next.length > 0
        ? `Folder Auth\n${next.map((x) => `${x.path} (${x.permission})`).join("\n")}`
        : "Folder Auth\nnone";
    setNodes((prev) =>
      prev.map((node) => {
        if (node.id !== "auth-node") return node;
        return { ...node, data: { ...node.data, label } };
      })
    );
  }

  function addFlowFolderAuth() {
    const path = flowFolderPathInput.trim();
    if (!path) return;
    const permission = normalizePermission(flowFolderPermInput);
    const exists = flowFolderAuths.some((x) => x.path === path);
    const next = exists
      ? flowFolderAuths.map((x) => (x.path === path ? { ...x, permission } : x))
      : [...flowFolderAuths, { path, permission }];
    applyFlowFolderAuths(next);
    setFlowFolderPermInput(permission);
    setFlowFolderPathInput("");
  }

  function removeFlowFolderAuth(path: string) {
    applyFlowFolderAuths(flowFolderAuths.filter((x) => x.path !== path));
  }

  async function pickFolderPath() {
    if (!editable) return;
    const picker = (window as Window & { showDirectoryPicker?: () => Promise<{ name?: string }> }).showDirectoryPicker;
    if (!picker) return;
    try {
      const handle = await picker();
      if (handle?.name) {
        setFlowFolderPathInput(handle.name);
      }
    } catch {
      // User canceled directory picker.
    }
  }

  return {
    open,
    close,
    title,
    editable,
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    flowSkills,
    flowSkillInput,
    setFlowSkillInput,
    addFlowSkill,
    removeFlowSkill,
    flowFolderAuths,
    flowFolderPathInput,
    setFlowFolderPathInput,
    flowFolderPermInput,
    setFlowFolderPermInput,
    addFlowFolderAuth,
    removeFlowFolderAuth,
    pickFolderPath,
    openTaskFlow,
  };
}
