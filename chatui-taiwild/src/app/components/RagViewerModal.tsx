"use client";

import { useMemo, useState } from "react";
import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import AppButton from "@/components/ui/AppButton";
import AppModal from "@/components/ui/AppModal";

type RagGraphNode = {
  id: string;
  type: string;
  label: string;
  meta: Record<string, unknown>;
};

type RagGraphEdge = {
  id: string;
  source: string;
  target: string;
};

type RagDocument = {
  documentId: string;
  scope: string;
  title: string;
  source?: string;
  tags?: string[];
  content?: string;
  chunks?: Array<{ chunkId: string; chunkIndex: number; content: string }>;
  updatedAt?: string;
};

type Props = {
  open: boolean;
  onClose: () => void;
  tenantId: string;
  loading: boolean;
  error: string | null;
  selectedScope: string;
  setSelectedScope: (value: string) => void;
  scopes: string[];
  documents: RagDocument[];
  graph: { nodes: RagGraphNode[]; edges: RagGraphEdge[] } | null;
  onRefresh: () => Promise<void>;
  onAddDocument: (payload: {
    scope: string;
    title: string;
    content: string;
    source: string;
    tags: string[];
  }) => Promise<void>;
};

function buildFlowGraph(graph: Props["graph"]): { nodes: Node[]; edges: Edge[] } {
  if (!graph) return { nodes: [], edges: [] };

  const scopeNodes = graph.nodes.filter((node) => node.type === "scope");
  const docNodes = graph.nodes.filter((node) => node.type === "document");
  const chunkNodes = graph.nodes.filter((node) => node.type === "chunk");

  const docByScope = new Map<string, RagGraphNode[]>();
  for (const edge of graph.edges) {
    if (!edge.source.startsWith("scope:") || !edge.target.startsWith("document:")) continue;
    const list = docByScope.get(edge.source) ?? [];
    const doc = docNodes.find((node) => node.id === edge.target);
    if (doc) list.push(doc);
    docByScope.set(edge.source, list);
  }

  const chunkByDoc = new Map<string, RagGraphNode[]>();
  for (const edge of graph.edges) {
    if (!edge.source.startsWith("document:") || !edge.target.startsWith("chunk:")) continue;
    const list = chunkByDoc.get(edge.source) ?? [];
    const chunk = chunkNodes.find((node) => node.id === edge.target);
    if (chunk) list.push(chunk);
    chunkByDoc.set(edge.source, list);
  }

  const nodes: Node[] = [];
  const edges: Edge[] = graph.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    animated: false,
    style: { stroke: "#a1a1aa" },
  }));

  scopeNodes.forEach((scopeNode, scopeIndex) => {
    nodes.push({
      id: scopeNode.id,
      position: { x: 20, y: 40 + scopeIndex * 220 },
      data: { label: scopeNode.label, meta: scopeNode.meta },
      type: "default",
      style: {
        width: 160,
        border: "1px solid #c084fc",
        background: "#faf5ff",
        color: "#6b21a8",
      },
    });
    const docs = docByScope.get(scopeNode.id) ?? [];
    docs.forEach((docNode, docIndex) => {
      const y = 20 + scopeIndex * 220 + docIndex * 90;
      nodes.push({
        id: docNode.id,
        position: { x: 250, y },
        data: { label: docNode.label, meta: docNode.meta },
        type: "default",
        style: {
          width: 220,
          border: "1px solid #0ea5e9",
          background: "#f0f9ff",
          color: "#0c4a6e",
        },
      });
      const chunks = chunkByDoc.get(docNode.id) ?? [];
      chunks.forEach((chunkNode, chunkIndex) => {
        nodes.push({
          id: chunkNode.id,
          position: { x: 540, y: y + chunkIndex * 74 },
          data: { label: chunkNode.label, meta: chunkNode.meta },
          type: "default",
          style: {
            width: 260,
            border: "1px solid #a3a3a3",
            background: "#fafafa",
            color: "#27272a",
            fontSize: 11,
          },
        });
      });
    });
  });

  return { nodes, edges };
}

export default function RagViewerModal(props: Props) {
  const [title, setTitle] = useState("");
  const [scopeInput, setScopeInput] = useState("");
  const [source, setSource] = useState("");
  const [tags, setTags] = useState("");
  const [content, setContent] = useState("");
  const [selectedNode, setSelectedNode] = useState<Record<string, unknown> | null>(null);

  const flow = useMemo(() => buildFlowGraph(props.graph), [props.graph]);

  const onNodeClick: NodeMouseHandler = (_, node) => {
    setSelectedNode((node.data?.meta as Record<string, unknown>) ?? null);
  };

  if (!props.open) return null;

  return (
    <AppModal panelClassName="w-full max-w-[95vw] h-[88vh] bg-white dark:bg-zinc-900 rounded border border-zinc-300 dark:border-zinc-700 flex flex-col">
      <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-700 flex items-center gap-2">
        <div className="font-medium flex-1">RAG Viewer</div>
        <div className="text-xs text-zinc-500 font-mono">{props.tenantId}</div>
        <AppButton type="button" onClick={() => void props.onRefresh()}>
          Refresh
        </AppButton>
        <AppButton type="button" onClick={props.onClose}>
          关闭
        </AppButton>
      </div>

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-[240px_1fr_320px] min-h-0">
        <aside className="border-r border-zinc-200 dark:border-zinc-700 p-3 overflow-auto">
          <div className="text-sm font-medium">Scopes</div>
          <div className="mt-2 space-y-1">
            <button
              type="button"
              className={`w-full text-left text-xs rounded px-2 py-1 border ${
                props.selectedScope === ""
                  ? "border-indigo-500 text-indigo-700 bg-indigo-50"
                  : "border-zinc-200 dark:border-zinc-700"
              }`}
              onClick={() => props.setSelectedScope("")}
            >
              All
            </button>
            {props.scopes.map((scope) => (
              <button
                key={scope}
                type="button"
                className={`w-full text-left text-xs rounded px-2 py-1 border ${
                  props.selectedScope === scope
                    ? "border-indigo-500 text-indigo-700 bg-indigo-50"
                    : "border-zinc-200 dark:border-zinc-700"
                }`}
                onClick={() => props.setSelectedScope(scope)}
              >
                {scope}
              </button>
            ))}
          </div>

          <div className="mt-4 border-t border-zinc-200 dark:border-zinc-700 pt-3">
            <div className="text-sm font-medium">Add Document</div>
            <div className="mt-2 space-y-2">
              <input
                className="w-full border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs bg-white dark:bg-zinc-900"
                placeholder="scope"
                value={scopeInput}
                onChange={(e) => setScopeInput(e.target.value)}
              />
              <input
                className="w-full border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs bg-white dark:bg-zinc-900"
                placeholder="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
              <input
                className="w-full border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs bg-white dark:bg-zinc-900"
                placeholder="source"
                value={source}
                onChange={(e) => setSource(e.target.value)}
              />
              <input
                className="w-full border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs bg-white dark:bg-zinc-900"
                placeholder="tags comma separated"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
              />
              <textarea
                className="w-full min-h-40 border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs bg-white dark:bg-zinc-900"
                placeholder="content"
                value={content}
                onChange={(e) => setContent(e.target.value)}
              />
              <AppButton
                type="button"
                size="sm"
                variant="success"
                onClick={async () => {
                  await props.onAddDocument({
                    scope: scopeInput,
                    title,
                    content,
                    source,
                    tags: tags
                      .split(",")
                      .map((item) => item.trim())
                      .filter((item) => item.length > 0),
                  });
                  setTitle("");
                  setScopeInput("");
                  setSource("");
                  setTags("");
                  setContent("");
                }}
                disabled={!scopeInput.trim() || !title.trim() || !content.trim()}
              >
                Add
              </AppButton>
            </div>
          </div>
        </aside>

        <section className="min-h-0 border-r border-zinc-200 dark:border-zinc-700">
          {props.loading ? (
            <div className="h-full flex items-center justify-center text-sm text-zinc-500">Loading...</div>
          ) : (
            <ReactFlow nodes={flow.nodes} edges={flow.edges} fitView onNodeClick={onNodeClick}>
              <Controls />
              <Background />
            </ReactFlow>
          )}
        </section>

        <aside className="p-3 overflow-auto">
          <div className="text-sm font-medium">Details</div>
          {props.error ? <div className="mt-2 text-xs text-red-600">{props.error}</div> : null}
          {selectedNode ? (
            <pre className="mt-2 text-[11px] whitespace-pre-wrap break-words rounded bg-zinc-50 dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-700 p-3">
              {JSON.stringify(selectedNode, null, 2)}
            </pre>
          ) : (
            <div className="mt-2 text-xs text-zinc-500">Click a graph node to inspect metadata.</div>
          )}

          <div className="mt-4 border-t border-zinc-200 dark:border-zinc-700 pt-3">
            <div className="text-sm font-medium">Documents</div>
            <div className="mt-2 space-y-2">
              {props.documents.map((doc) => (
                <button
                  key={doc.documentId}
                  type="button"
                  className="w-full text-left text-xs rounded border border-zinc-200 dark:border-zinc-700 px-2 py-2"
                  onClick={() =>
                    setSelectedNode({
                      documentId: doc.documentId,
                      scope: doc.scope,
                      title: doc.title,
                      source: doc.source,
                      tags: doc.tags,
                      updatedAt: doc.updatedAt,
                      content: doc.content,
                    })
                  }
                >
                  <div className="font-medium">{doc.title}</div>
                  <div className="text-zinc-500 mt-1">{doc.scope}</div>
                </button>
              ))}
              {props.documents.length === 0 ? (
                <div className="text-xs text-zinc-500">No documents in current scope.</div>
              ) : null}
            </div>
          </div>
        </aside>
      </div>
    </AppModal>
  );
}
