"use client";

import { useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
  type Connection,
  type OnEdgesChange,
  type OnNodesChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import AppButton from "@/components/ui/AppButton";
import AppModal from "@/components/ui/AppModal";

type SkillNodeData = {
  skills: string[];
  editable: boolean;
  onAddSkill?: (skill: string) => void;
  onRemoveSkill?: (skill: string) => void;
};

function SkillNode({ data }: NodeProps<Node<SkillNodeData>>) {
  const [value, setValue] = useState("");
  return (
    <div className="min-w-[220px] border border-amber-400 bg-amber-100 rounded p-2 text-xs text-amber-900">
      <div className="font-medium mb-1">Skills Node</div>
      <div className="space-y-1 mb-2">
        {data.skills.length > 0 ? (
          data.skills.map((s) => (
            <div key={s} className="flex items-center justify-between gap-2">
              <span>{s}</span>
              {data.editable ? (
                <AppButton type="button" size="xs" variant="danger" onClick={() => data.onRemoveSkill?.(s)}>
                  x
                </AppButton>
              ) : null}
            </div>
          ))
        ) : (
          <div className="text-amber-700/70">none</div>
        )}
      </div>
      {data.editable ? (
        <div className="flex items-center gap-1">
          <input
            className="flex-1 border border-amber-500 rounded px-1 py-0.5 bg-amber-50"
            placeholder="add skill"
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
          <AppButton
            type="button"
            size="xs"
            className="border-amber-600"
            onClick={() => {
              const next = value.trim();
              if (!next) return;
              data.onAddSkill?.(next);
              setValue("");
            }}
          >
            add
          </AppButton>
        </div>
      ) : null}
    </div>
  );
}

const nodeTypes: NodeTypes = { skillNode: SkillNode };

type Props = {
  open: boolean;
  title: string;
  editable: boolean;
  nodes: Node[];
  edges: Edge[];
  onClose: () => void;
  onNodesChange: OnNodesChange<Node>;
  onEdgesChange: OnEdgesChange<Edge>;
  onConnect: (params: Connection) => void;
  flowSkills: string[];
  flowSkillInput: string;
  setFlowSkillInput: (value: string) => void;
  addFlowSkill: () => void;
  removeFlowSkill: (skill: string) => void;
  flowFolderAuths: Array<{ path: string; permission: string }>;
  flowFolderPathInput: string;
  setFlowFolderPathInput: (value: string) => void;
  flowFolderPermInput: string;
  setFlowFolderPermInput: (value: string) => void;
  addFlowFolderAuth: () => void;
  removeFlowFolderAuth: (path: string) => void;
  pickFolderPath: () => void | Promise<void>;
};

export default function TaskFlowModal(props: Props) {
  if (!props.open) return null;
  return (
    <AppModal
      zIndexClass="z-tooltip"
      overlayClassName="task-flow-modal"
      panelClassName="w-full max-w-6xl h-[80vh] bg-white dark:bg-zinc-900 rounded border border-zinc-300 dark:border-zinc-700 flex flex-col"
    >
        <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-700 flex items-center gap-2">
          <div className="font-medium flex-1">Task Flow: {props.title}</div>
          <div className="text-xs text-zinc-500">{props.editable ? "可编辑模式" : "查看模式"}</div>
          <input
            className="border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs w-44"
            placeholder="add skill..."
            value={props.flowSkillInput}
            onChange={(e) => props.setFlowSkillInput(e.target.value)}
            disabled={!props.editable}
          />
          <AppButton type="button" size="sm" onClick={props.addFlowSkill} disabled={!props.editable}>
            添加 Skill
          </AppButton>
          <AppButton type="button" size="sm" onClick={props.onClose}>
            关闭
          </AppButton>
        </div>
        <div className="px-4 py-2 border-b border-zinc-200 dark:border-zinc-700 flex items-center gap-2 flex-wrap">
          <div className="text-xs text-zinc-500">Skills:</div>
          {props.flowSkills.length === 0 ? (
            <div className="text-xs text-zinc-400">none</div>
          ) : (
            props.flowSkills.map((s) => (
              <div
                key={s}
                className="text-xs border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 flex items-center gap-1"
              >
                <span>{s}</span>
                {props.editable ? (
                  <AppButton type="button" size="xs" variant="danger" onClick={() => props.removeFlowSkill(s)}>
                    x
                  </AppButton>
                ) : null}
              </div>
            ))
          )}
        </div>
        <div className="px-4 py-2 border-b border-zinc-200 dark:border-zinc-700">
          <div className="text-xs text-zinc-500 mb-2">本地文件夹授权（路径 + Linux 权限）</div>
          <div className="flex items-center gap-2 flex-wrap mb-2">
            <input
              className="border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs w-[340px]"
              placeholder="/home/user/project"
              value={props.flowFolderPathInput}
              onChange={(e) => props.setFlowFolderPathInput(e.target.value)}
              disabled={!props.editable}
            />
            <input
              className="border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs w-20 text-center"
              placeholder="777"
              value={props.flowFolderPermInput}
              onChange={(e) => props.setFlowFolderPermInput(e.target.value)}
              disabled={!props.editable}
            />
            <AppButton type="button" size="xs" onClick={props.pickFolderPath} disabled={!props.editable}>
              选择文件夹
            </AppButton>
            <AppButton type="button" size="xs" variant="info" onClick={props.addFlowFolderAuth} disabled={!props.editable}>
              添加授权
            </AppButton>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {props.flowFolderAuths.length === 0 ? (
              <div className="text-xs text-zinc-400">none</div>
            ) : (
              props.flowFolderAuths.map((item) => (
                <div
                  key={`${item.path}-${item.permission}`}
                  className="text-xs border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 flex items-center gap-1"
                >
                  <span>{item.path}</span>
                  <span className="text-zinc-500">({item.permission})</span>
                  {props.editable ? (
                    <AppButton type="button" size="xs" variant="danger" onClick={() => props.removeFlowFolderAuth(item.path)}>
                      x
                    </AppButton>
                  ) : null}
                </div>
              ))
            )}
          </div>
        </div>
        <div className="flex-1">
          <ReactFlow
            nodes={props.nodes}
            edges={props.edges}
            nodeTypes={nodeTypes}
            onNodesChange={props.editable ? props.onNodesChange : undefined}
            onEdgesChange={props.editable ? props.onEdgesChange : undefined}
            onConnect={props.onConnect}
            nodesDraggable={props.editable}
            elementsSelectable
            fitView
          >
            <MiniMap
              pannable
              nodeColor={() => "#d6b36a"}
              maskColor="rgba(160, 120, 40, 0.18)"
              style={{ backgroundColor: "#f8eed4", border: "1px solid #d6b36a" }}
            />
            <Controls style={{ backgroundColor: "#f8eed4", border: "1px solid #d6b36a" }} />
            <Background />
          </ReactFlow>
        </div>
    </AppModal>
  );
}
