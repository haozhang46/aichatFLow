"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from "d3";
import * as yup from "yup";
import {
  Background,
  BaseEdge,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  getBezierPath,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import AppButton from "@/components/ui/AppButton";
import BaseForm, { BaseField, BaseSelect, BaseTextarea } from "@/components/ui/BaseForm";
import AppModal from "@/components/ui/AppModal";
import { ragGraphTheme } from "@/components/ui/theme";

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

type ForceGraphNodeData = {
  id: string;
  name: string;
  type: string;
  meta: Record<string, unknown>;
  color: string;
  val: number;
  opacity: number;
  ring: number;
  inner: number;
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
};

type ForceGraphLinkData = {
  id: string;
  source: string | ForceGraphNodeData;
  target: string | ForceGraphNodeData;
  color: string;
  width: number;
  relationType: "hierarchy" | "tag" | "source" | "similar";
  opacity: number;
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

type DocumentFormValues = {
  scope: string;
  title: string;
  source: string;
  tags: string;
  content: string;
};

type FlowEditorNodeData = {
  label: string;
  meta: Record<string, unknown>;
  kind: "scope" | "document" | "chunk";
  accent: string;
  chipLabel: string;
  summary: string;
  stats: string[];
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
  onCreateScope: (scope: string) => Promise<void>;
  onAddDocument: (payload: {
    scope: string;
    title: string;
    content: string;
    source: string;
    tags: string[];
  }) => Promise<void>;
  onUpdateDocument: (payload: {
    documentId: string;
    scope: string;
    title: string;
    content: string;
    source: string;
    tags: string[];
  }) => Promise<void>;
  onDeleteDocument: (documentId: string) => Promise<void>;
  onBatchIngest: (payload: {
    scope: string;
    items: Array<{
      scope?: string;
      title?: string;
      content?: string;
      url?: string;
      filePath?: string;
      source?: string;
      tags?: string[];
    }>;
  }) => Promise<void>;
  onUploadFiles: (payload: { scope: string; files: File[]; tags: string[] }) => Promise<void>;
};

const documentSchema = yup.object({
  scope: yup.string().trim().required("请输入 scope"),
  title: yup.string().trim().required("请输入 title"),
  source: yup.string().trim().default(""),
  tags: yup.string().default(""),
  content: yup.string().trim().required("请输入内容"),
});

function parseTags(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function buildScopeOptions(scopes: string[], selectedScope: string) {
  return Array.from(new Set([selectedScope.trim(), ...scopes.map((scope) => scope.trim())].filter(Boolean)));
}

function buildDocumentMeta(doc: RagDocument) {
  return {
    documentId: doc.documentId,
    scope: doc.scope,
    title: doc.title,
    source: doc.source,
    tags: doc.tags,
    updatedAt: doc.updatedAt,
    content: doc.content,
  };
}

function buildDocumentDraft(doc: RagDocument): DocumentFormValues {
  return {
    title: doc.title,
    scope: doc.scope,
    source: doc.source ?? "",
    tags: (doc.tags ?? []).join(", "),
    content: doc.content ?? "",
  };
}

function pickNodeColor(type: string) {
  if (type === "scope") return ragGraphTheme.node.scope;
  if (type === "document") return ragGraphTheme.node.document;
  return ragGraphTheme.node.chunk;
}

function pickNodeSize(type: string) {
  if (type === "scope") return 18;
  if (type === "document") return 12;
  return 8;
}

function pickNodeRingSize(type: string) {
  if (type === "scope") return 22;
  if (type === "document") return 14;
  return 9.5;
}

function pickNodeInnerSize(type: string) {
  if (type === "scope") return 8;
  if (type === "document") return 4.8;
  return 3.4;
}

function pickNodeTypeLabel(type: string) {
  if (type === "scope") return "Scope";
  if (type === "document") return "Document";
  return "Chunk";
}

function truncateLabel(value: string, max = 30) {
  return value.length > max ? `${value.slice(0, max)}...` : value;
}

function normalizeTagList(tags: unknown) {
  return Array.isArray(tags)
    ? tags.map((tag) => String(tag).trim()).filter((tag) => tag.length > 0)
    : [];
}

function tokenizeContent(content: string | undefined) {
  return String(content ?? "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .map((token) => token.trim())
    .filter((token) => token.length >= 4)
    .slice(0, 80);
}

function buildGraphMaps(graph: NonNullable<Props["graph"]>) {
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

  return { scopeNodes, docNodes, docByScope, chunkByDoc };
}

function buildFlowSummary(kind: FlowEditorNodeData["kind"], meta: Record<string, unknown>) {
  if (kind === "scope") {
    return `Scope workspace · ${String(meta.scope ?? "").trim() || "unscoped"}`;
  }
  if (kind === "document") {
    const source = String(meta.source ?? "").trim();
    return source || "Document knowledge item";
  }
  const documentId = String(meta.documentId ?? "").trim();
  return documentId ? `Chunk of ${documentId}` : "Chunk segment";
}

function buildFlowStats(kind: FlowEditorNodeData["kind"], meta: Record<string, unknown>) {
  if (kind === "scope") {
    const scope = String(meta.scope ?? "").trim();
    return [scope || "default", "entry"];
  }
  if (kind === "document") {
    const tags = Array.isArray(meta.tags) ? meta.tags.length : 0;
    const updatedAt = String(meta.updatedAt ?? "").trim();
    return [`${tags} tag${tags === 1 ? "" : "s"}`, updatedAt ? "tracked" : "draft"];
  }
  const chunkIndex = meta.chunkIndex;
  return [typeof chunkIndex === "number" ? `chunk ${chunkIndex + 1}` : "chunk", "segment"];
}

function FlowEditorNode({ data, selected }: NodeProps<Node<FlowEditorNodeData>>) {
  return (
    <div
      className="min-w-[250px] max-w-[280px] rounded-2xl border bg-white shadow-[0_22px_55px_-30px_rgba(15,23,42,0.45)]"
      style={{
        borderColor: selected ? data.accent : "rgba(148,163,184,0.28)",
        boxShadow: selected
          ? `0 24px 60px -30px ${data.accent}55`
          : "0 20px 48px -34px rgba(15,23,42,0.38)",
      }}
    >
      <Handle type="target" position={Position.Left} className="!h-3 !w-3 !border-2 !border-white" style={{ background: data.accent }} />
      <div className="rounded-t-2xl px-4 py-3 text-white" style={{ background: `linear-gradient(135deg, ${data.accent}, ${data.accent}cc)` }}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-white/80">{data.chipLabel}</div>
            <div className="mt-1 truncate text-sm font-semibold">{data.label}</div>
          </div>
          <div className="rounded-full border border-white/25 bg-white/14 px-2 py-1 text-[10px] font-medium">{data.kind}</div>
        </div>
      </div>
      <div className="px-4 py-3">
        <div className="text-[11px] leading-5 text-slate-500">{data.summary}</div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {data.stats.map((item) => (
            <span key={item} className="rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-[10px] font-medium text-slate-600">
              {item}
            </span>
          ))}
        </div>
      </div>
      <Handle type="source" position={Position.Right} className="!h-3 !w-3 !border-2 !border-white" style={{ background: data.accent }} />
    </div>
  );
}

function FlowEditorEdge(props: EdgeProps<Edge>) {
  const [path] = getBezierPath({
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    sourcePosition: props.sourcePosition,
    targetX: props.targetX,
    targetY: props.targetY,
    targetPosition: props.targetPosition,
  });

  return <BaseEdge path={path} style={{ stroke: "#94a3b8", strokeWidth: 1.35, strokeOpacity: 0.82 }} />;
}

const flowNodeTypes: NodeTypes = {
  flowEditorNode: FlowEditorNode,
};

function buildTreeFlowGraph(graph: Props["graph"]): { nodes: Node<FlowEditorNodeData>[]; edges: Edge[] } {
  if (!graph) return { nodes: [], edges: [] };
  const { scopeNodes, docByScope, chunkByDoc } = buildGraphMaps(graph);

  const nodes: Node<FlowEditorNodeData>[] = [];
  const edges: Edge[] = graph.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    animated: false,
    type: "flowEditorEdge",
    style: { stroke: "#94a3b8", strokeWidth: 1.35 },
  }));

  scopeNodes.forEach((scopeNode, scopeIndex) => {
    const docs = docByScope.get(scopeNode.id) ?? [];
    nodes.push({
      id: scopeNode.id,
      position: { x: 40, y: 80 + scopeIndex * 300 },
      data: {
        label: scopeNode.label,
        meta: scopeNode.meta,
        kind: "scope",
        accent: "#ff6b6b",
        chipLabel: "Scope Node",
        summary: buildFlowSummary("scope", scopeNode.meta),
        stats: [...buildFlowStats("scope", scopeNode.meta), `${docs.length} docs`],
      },
      type: "flowEditorNode",
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    });
    docs.forEach((docNode, docIndex) => {
      const y = 40 + scopeIndex * 300 + docIndex * 160;
      const chunks = chunkByDoc.get(docNode.id) ?? [];
      nodes.push({
        id: docNode.id,
        position: { x: 360, y },
        data: {
          label: docNode.label,
          meta: docNode.meta,
          kind: "document",
          accent: "#4ecdc4",
          chipLabel: "Document Node",
          summary: buildFlowSummary("document", docNode.meta),
          stats: [...buildFlowStats("document", docNode.meta), `${chunks.length} chunks`],
        },
        type: "flowEditorNode",
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      });
      chunks.forEach((chunkNode, chunkIndex) => {
        nodes.push({
          id: chunkNode.id,
          position: { x: 720, y: y + chunkIndex * 124 },
          data: {
            label: chunkNode.label,
            meta: chunkNode.meta,
            kind: "chunk",
            accent: "#3b82f6",
            chipLabel: "Chunk Node",
            summary: buildFlowSummary("chunk", chunkNode.meta),
            stats: buildFlowStats("chunk", chunkNode.meta),
          },
          type: "flowEditorNode",
          sourcePosition: Position.Right,
          targetPosition: Position.Left,
        });
      });
    });
  });

  return { nodes, edges };
}

function buildForceGraphData(
  graph: Props["graph"],
  documents: RagDocument[],
  selectedGraphNodeId: string | null,
  selectedDocumentId: string,
  relationFilters: Record<ForceGraphLinkData["relationType"], boolean>
): { nodes: ForceGraphNodeData[]; links: ForceGraphLinkData[]; neighborIds: Set<string> } {
  if (!graph) return { nodes: [], links: [], neighborIds: new Set<string>() };
  const expandedDocumentNodeId = selectedDocumentId ? `document:${selectedDocumentId}` : "";
  const baseNodes = graph.nodes.filter((node) => {
    if (node.type !== "chunk") return true;
    return expandedDocumentNodeId ? String(node.meta.documentId ?? "") === selectedDocumentId : false;
  });

  const baseLinks = graph.edges.filter((edge) => {
    if (!edge.target.startsWith("chunk:")) return true;
    return expandedDocumentNodeId ? edge.source === expandedDocumentNodeId : false;
  });

  const relationLinks: ForceGraphLinkData[] = [];
  for (let i = 0; i < documents.length; i += 1) {
    for (let j = i + 1; j < documents.length; j += 1) {
      const left = documents[i];
      const right = documents[j];
      const leftNodeId = `document:${left.documentId}`;
      const rightNodeId = `document:${right.documentId}`;
      if (!baseNodes.some((node) => node.id === leftNodeId) || !baseNodes.some((node) => node.id === rightNodeId)) continue;

      const leftTags = normalizeTagList(left.tags);
      const rightTags = normalizeTagList(right.tags);
      const sharedTags = leftTags.filter((tag) => rightTags.includes(tag));
      if (sharedTags.length > 0) {
        relationLinks.push({
          id: `edge:tag:${left.documentId}:${right.documentId}`,
          source: leftNodeId,
          target: rightNodeId,
          color: ragGraphTheme.edge.tag,
          width: 0.6 + Math.min(sharedTags.length * 0.25, 0.9),
          relationType: "tag",
          opacity: 1,
        });
      }

      const leftSource = String(left.source ?? "").trim();
      const rightSource = String(right.source ?? "").trim();
      if (leftSource && rightSource && leftSource === rightSource) {
        relationLinks.push({
          id: `edge:source:${left.documentId}:${right.documentId}`,
          source: leftNodeId,
          target: rightNodeId,
          color: ragGraphTheme.edge.source,
          width: 0.65,
          relationType: "source",
          opacity: 1,
        });
      }

      const leftTokens = tokenizeContent(left.content);
      const rightTokens = tokenizeContent(right.content);
      const sharedTokens = leftTokens.filter((token) => rightTokens.includes(token));
      if (sharedTokens.length >= 3) {
        relationLinks.push({
          id: `edge:similar:${left.documentId}:${right.documentId}`,
          source: leftNodeId,
          target: rightNodeId,
          color: ragGraphTheme.edge.similar,
          width: 0.75 + Math.min(sharedTokens.length / 10, 0.85),
          relationType: "similar",
          opacity: 1,
        });
      }
    }
  }

  const links: ForceGraphLinkData[] = [
    ...baseLinks.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      color: edge.source.startsWith("scope:") ? ragGraphTheme.edge.hierarchyScope : ragGraphTheme.edge.hierarchyChunk,
      width: edge.source.startsWith("scope:") ? 0.9 : 0.55,
      relationType: "hierarchy" as const,
      opacity: 1,
    })),
    ...relationLinks,
  ].filter((link) => relationFilters[link.relationType]);

  const neighborIds = new Set<string>();
  if (selectedGraphNodeId) {
    neighborIds.add(selectedGraphNodeId);
    links.forEach((link) => {
      const sourceId = String(link.source);
      const targetId = String(link.target);
      if (sourceId === selectedGraphNodeId) neighborIds.add(targetId);
      if (targetId === selectedGraphNodeId) neighborIds.add(sourceId);
    });
  }

  const nodes = baseNodes.map((node) => ({
    id: node.id,
    name: node.label,
    type: node.type,
    meta: node.meta,
    color: pickNodeColor(node.type),
    val: pickNodeSize(node.type),
    ring: pickNodeRingSize(node.type),
    inner: pickNodeInnerSize(node.type),
    opacity: selectedGraphNodeId && !neighborIds.has(node.id) ? 0.18 : 1,
  }));

  const decoratedLinks = links.map((link) => {
    const sourceId = String(link.source);
    const targetId = String(link.target);
    const active = !selectedGraphNodeId || sourceId === selectedGraphNodeId || targetId === selectedGraphNodeId;
    return {
      ...link,
      opacity: active ? 1 : 0.12,
    };
  });

  return { nodes, links: decoratedLinks, neighborIds };
}

export default function RagViewerModal(props: Props) {
  const [viewMode, setViewMode] = useState<"graph" | "tree">("graph");
  const [refreshing, setRefreshing] = useState(false);
  const [creatingScope, setCreatingScope] = useState(false);
  const [batchScope, setBatchScope] = useState("");
  const [batchUrls, setBatchUrls] = useState("");
  const [batchFiles, setBatchFiles] = useState("");
  const [batchUploadTags, setBatchUploadTags] = useState("");
  const [selectedUploadFiles, setSelectedUploadFiles] = useState<File[]>([]);
  const [batchSubmitting, setBatchSubmitting] = useState(false);
  const [uploadingFiles, setUploadingFiles] = useState(false);
  const [newScope, setNewScope] = useState("");
  const [graphSearch, setGraphSearch] = useState("");
  const [hoveredGraphNodeId, setHoveredGraphNodeId] = useState<string | null>(null);
  const [relationFilters, setRelationFilters] = useState<Record<ForceGraphLinkData["relationType"], boolean>>({
    hierarchy: true,
    tag: true,
    source: true,
    similar: true,
  });
  const [selectedGraphNodeId, setSelectedGraphNodeId] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<Record<string, unknown> | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [selectedDocumentDraft, setSelectedDocumentDraft] = useState<DocumentFormValues | null>(null);
  const [deletingDocument, setDeletingDocument] = useState(false);
  const [deletingDocumentId, setDeletingDocumentId] = useState<string | null>(null);
  const [forceStrength, setForceStrength] = useState(170);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const graphViewportRef = useRef<HTMLDivElement | null>(null);
  const [graphViewport, setGraphViewport] = useState({ width: 0, height: 0 });
  const scopeOptions = useMemo(() => buildScopeOptions(props.scopes, props.selectedScope), [props.scopes, props.selectedScope]);
  const effectiveBatchScope = batchScope.trim() || props.selectedScope || "";
  const effectiveGraphWidth = graphViewport.width > 0 ? graphViewport.width : 960;
  const effectiveGraphHeight = graphViewport.height > 0 ? graphViewport.height : 720;

  const flow = useMemo(() => buildTreeFlowGraph(props.graph), [props.graph]);
  const forceGraph = useMemo(
    () => buildForceGraphData(props.graph, props.documents, selectedGraphNodeId, selectedDocumentId, relationFilters),
    [props.graph, props.documents, selectedGraphNodeId, selectedDocumentId, relationFilters]
  );

  useEffect(() => {
    const element = graphViewportRef.current;
    if (!element) return;
    const updateSize = () => {
      const rect = element.getBoundingClientRect();
      setGraphViewport({
        width: Math.max(0, Math.floor(rect.width || element.clientWidth)),
        height: Math.max(0, Math.floor(rect.height || element.clientHeight)),
      });
    };
    updateSize();
    const observer = new ResizeObserver(() => updateSize());
    observer.observe(element);
    window.addEventListener("resize", updateSize);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", updateSize);
    };
  }, [props.open, viewMode]);

  const [graphLayout, setGraphLayout] = useState<{ nodes: ForceGraphNodeData[]; links: ForceGraphLinkData[] }>({
    nodes: [],
    links: [],
  });

  useEffect(() => {
    if (viewMode !== "graph") return;

    const nodes = forceGraph.nodes.map((node) => ({ ...node }));
    const links = forceGraph.links.map((link) => ({ ...link }));

    const simulation = forceSimulation(nodes)
      .force(
        "link",
        forceLink<ForceGraphNodeData, ForceGraphLinkData>(links)
          .id((node: ForceGraphNodeData) => node.id)
          .distance((link: ForceGraphLinkData) => {
            if (link.relationType === "hierarchy") return String(link.target).startsWith("chunk:") ? 78 : 124;
            if (link.relationType === "similar") return 150;
            return 132;
          })
      )
      .force(
        "charge",
        forceManyBody<ForceGraphNodeData>().strength((node: ForceGraphNodeData) => {
          if (node.type === "chunk") return -Math.max(45, forceStrength * 0.42);
          if (node.type === "scope") return -forceStrength * 1.45;
          return -forceStrength;
        })
      )
      .force("collision", forceCollide<ForceGraphNodeData>().radius((node) => node.ring + 16).strength(0.9))
      .force("x", forceX(effectiveGraphWidth / 2).strength(0.04))
      .force("y", forceY(effectiveGraphHeight / 2).strength(0.04));

    simulation.stop();
    for (let i = 0; i < 120; i += 1) {
      simulation.tick();
    }
    setGraphLayout({
      nodes: nodes.map((node) => ({ ...node })),
      links: links.map((link) => ({ ...link })),
    });

    return () => {
      simulation.stop();
    };
  }, [effectiveGraphHeight, effectiveGraphWidth, forceGraph.links, forceGraph.nodes, forceStrength, viewMode]);

  useEffect(() => {
    if (!graphSearch.trim()) return;
    const keyword = graphSearch.trim().toLowerCase();
    const match = forceGraph.nodes.find((node) => node.name.toLowerCase().includes(keyword) || node.id.toLowerCase().includes(keyword));
    if (!match) return;
    setSelectedGraphNodeId(match.id);
    setSelectedNode(match.meta);
    if (match.id.startsWith("document:")) {
      setSelectedDocumentId(String(match.meta.documentId ?? ""));
      setSelectedDocumentDraft({
        title: String(match.meta.title ?? ""),
        scope: String(match.meta.scope ?? ""),
        source: String(match.meta.source ?? ""),
        tags: Array.isArray(match.meta.tags) ? match.meta.tags.map((x) => String(x)).join(", ") : "",
        content: String(match.meta.content ?? ""),
      });
    }
  }, [graphSearch, forceGraph.nodes]);

  async function handleDeleteSelectedDocument() {
    if (!selectedDocumentId) return;
    setDeletingDocument(true);
    setDeletingDocumentId(selectedDocumentId);
    try {
      await props.onDeleteDocument(selectedDocumentId);
      setSelectedDocumentId("");
      setSelectedGraphNodeId(null);
      setSelectedNode(null);
      setSelectedDocumentDraft(null);
    } finally {
      setDeletingDocument(false);
      setDeletingDocumentId(null);
    }
  }

  async function handleDeleteDocument(doc: RagDocument) {
    setDeletingDocument(true);
    setDeletingDocumentId(doc.documentId);
    try {
      await props.onDeleteDocument(doc.documentId);
      if (selectedDocumentId === doc.documentId) {
        setSelectedDocumentId("");
        setSelectedGraphNodeId(null);
        setSelectedNode(null);
        setSelectedDocumentDraft(null);
      }
    } finally {
      setDeletingDocument(false);
      setDeletingDocumentId(null);
    }
  }

  if (!props.open) return null;

  function resolveNodePosition(value: string | ForceGraphNodeData) {
    if (typeof value === "string") return graphLayout.nodes.find((node) => node.id === value) ?? null;
    return value;
  }

  function selectGraphNode(node: ForceGraphNodeData) {
    setSelectedGraphNodeId(node.id);
    setSelectedNode(node.meta);
    if (node.id.startsWith("document:")) {
      const documentId = String(node.meta.documentId ?? "");
      setSelectedDocumentId(documentId);
      setSelectedDocumentDraft({
        title: String(node.meta.title ?? ""),
        scope: String(node.meta.scope ?? ""),
        source: String(node.meta.source ?? ""),
        tags: Array.isArray(node.meta.tags) ? node.meta.tags.map((x) => String(x)).join(", ") : "",
        content: String(node.meta.content ?? ""),
      });
      return;
    }

    if (selectedDocumentId) {
      setSelectedDocumentId("");
      setSelectedDocumentDraft(null);
    }
  }

  return (
    <AppModal panelClassName="w-full max-w-[95vw] h-[88vh] bg-white dark:bg-zinc-900 rounded border border-zinc-300 dark:border-zinc-700 flex flex-col">
      <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-700 flex items-center gap-2">
        <div className="font-medium flex-1">RAG Viewer</div>
        <div className="text-xs text-zinc-500 font-mono">{props.tenantId}</div>
        {viewMode === "graph" ? (
          <input
            className="border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs bg-white dark:bg-zinc-900"
            placeholder="Search graph node..."
            value={graphSearch}
            onChange={(e) => setGraphSearch(e.target.value)}
          />
        ) : null}
        <div className="flex items-center gap-1 border border-zinc-300 dark:border-zinc-700 rounded p-0.5">
          <AppButton
            type="button"
            size="xs"
            variant="tab"
            className={viewMode === "graph" ? "bg-zinc-200 dark:bg-zinc-700" : ""}
            onClick={() => setViewMode("graph")}
          >
            Graph
          </AppButton>
          <AppButton
            type="button"
            size="xs"
            variant="tab"
            className={viewMode === "tree" ? "bg-zinc-200 dark:bg-zinc-700" : ""}
            onClick={() => setViewMode("tree")}
          >
            Tree
          </AppButton>
        </div>
        <AppButton
          type="button"
          loading={refreshing}
          loadingText="Refreshing..."
          onClick={async () => {
            setRefreshing(true);
            try {
              await props.onRefresh();
            } finally {
              setRefreshing(false);
            }
          }}
        >
          Refresh
        </AppButton>
        <AppButton type="button" onClick={props.onClose}>
          关闭
        </AppButton>
      </div>

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-[240px_1fr_320px] min-h-0">
        <aside className="border-r border-zinc-200 dark:border-zinc-700 p-3 overflow-auto">
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-medium">Scopes</div>
          </div>
          <div className="mt-2 flex items-center gap-2">
            <input
              className="w-full border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs bg-white dark:bg-zinc-900"
              placeholder="new scope"
              value={newScope}
              onChange={(e) => setNewScope(e.target.value)}
            />
            <AppButton
              type="button"
              size="xs"
              variant="info"
              loading={creatingScope}
              loadingText="Adding..."
              disabled={!newScope.trim()}
              onClick={async () => {
                const value = newScope.trim();
                if (!value) return;
                setCreatingScope(true);
                try {
                  await props.onCreateScope(value);
                  setNewScope("");
                } finally {
                  setCreatingScope(false);
                }
              }}
            >
              Add
            </AppButton>
          </div>
          {props.error ? <div className="mt-2 text-[11px] text-red-600 dark:text-red-400">{props.error}</div> : null}
          <div className="mt-2 space-y-1">
            <button
              type="button"
              className={`w-full text-left text-xs rounded px-2 py-1 border ${
                props.selectedScope === ""
                  ? "border-zinc-500 text-zinc-900 bg-zinc-100 dark:bg-zinc-800 dark:text-zinc-100"
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
                    ? "border-zinc-500 text-zinc-900 bg-zinc-100 dark:bg-zinc-800 dark:text-zinc-100"
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
            <BaseForm<DocumentFormValues>
              initialValues={{ scope: props.selectedScope || scopeOptions[0] || "", title: "", source: "", tags: "", content: "" }}
              validationSchema={documentSchema}
              onSubmit={async (values, helpers) => {
                await props.onAddDocument({
                  scope: values.scope.trim(),
                  title: values.title.trim(),
                  content: values.content.trim(),
                  source: values.source.trim(),
                  tags: parseTags(values.tags),
                });
                helpers.resetForm();
              }}
              enableReinitialize
              className="mt-2 space-y-2"
            >
              {({ isSubmitting, isValid }) => (
                <>
                  <BaseSelect name="scope" className="text-xs">
                    <option value="">选择 scope</option>
                    {scopeOptions.map((scope) => (
                      <option key={scope} value={scope}>
                        {scope}
                      </option>
                    ))}
                  </BaseSelect>
                  <BaseField name="title" placeholder="title" className="text-xs" />
                  <BaseField name="source" placeholder="source" className="text-xs" />
                  <BaseField name="tags" placeholder="tags comma separated" className="text-xs" />
                  <BaseTextarea
                    name="content"
                    placeholder="content"
                    className="text-xs"
                    rows={8}
                  />
                  <AppButton type="submit" size="sm" variant="success" loading={isSubmitting} loadingText="Adding..." disabled={!isValid}>
                    Add
                  </AppButton>
                </>
              )}
            </BaseForm>
          </div>

          <div className="mt-4 border-t border-zinc-200 dark:border-zinc-700 pt-3">
            <div className="text-sm font-medium">Batch Ingest</div>
            <div className="mt-2 space-y-2">
              <select
                className="w-full rounded border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-900 outline-none transition-colors focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                value={effectiveBatchScope}
                onChange={(e) => setBatchScope(e.target.value)}
              >
                <option value="">选择 default scope</option>
                {scopeOptions.map((scope) => (
                  <option key={`batch-${scope}`} value={scope}>
                    {scope}
                  </option>
                ))}
              </select>
              <textarea
                className="w-full min-h-24 border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs bg-white dark:bg-zinc-900"
                placeholder={"one url per line\nhttps://example.com/docs/a"}
                value={batchUrls}
                onChange={(e) => setBatchUrls(e.target.value)}
              />
              <textarea
                className="w-full min-h-24 border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs bg-white dark:bg-zinc-900"
                placeholder={"/absolute/or/relative/file.txt\n./notes/rules.md\n./docs/manual.pdf\n./docs/spec.docx\n./books/story.epub"}
                value={batchFiles}
                onChange={(e) => setBatchFiles(e.target.value)}
              />
              <div className="text-[11px] text-zinc-500">
                Server-side file path ingest. Supported: txt, md, json, csv, tsv, html, xml, pdf, docx, epub.
              </div>
              <input
                ref={uploadInputRef}
                type="file"
                multiple
                accept=".txt,.md,.markdown,.json,.jsonl,.yaml,.yml,.xml,.html,.htm,.csv,.tsv,.pdf,.docx,.epub"
                className="hidden"
                onChange={(e) => {
                  const next = Array.from(e.target.files ?? []);
                  setSelectedUploadFiles(next);
                }}
              />
              <input
                className="w-full border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs bg-white dark:bg-zinc-900"
                placeholder="upload tags comma separated"
                value={batchUploadTags}
                onChange={(e) => setBatchUploadTags(e.target.value)}
              />
              <div className="text-[11px] text-zinc-500">
                Browser upload files: {selectedUploadFiles.length > 0 ? selectedUploadFiles.map((file) => file.name).join(", ") : "none selected"}
              </div>
              <AppButton
                type="button"
                size="sm"
                variant="info"
                loading={batchSubmitting}
                loadingText="Ingesting..."
                disabled={!effectiveBatchScope.trim() || (!batchUrls.trim() && !batchFiles.trim())}
                onClick={async () => {
                  const items = [
                    ...batchUrls
                      .split("\n")
                      .map((item) => item.trim())
                      .filter((item) => item.length > 0)
                      .map((url) => ({ url, source: url })),
                    ...batchFiles
                      .split("\n")
                      .map((item) => item.trim())
                      .filter((item) => item.length > 0)
                      .map((filePath) => ({ filePath, source: filePath })),
                  ];
                  setBatchSubmitting(true);
                  try {
                    await props.onBatchIngest({ scope: effectiveBatchScope, items });
                    setBatchUrls("");
                    setBatchFiles("");
                  } finally {
                    setBatchSubmitting(false);
                  }
                }}
              >
                Batch Ingest
              </AppButton>
              <div className="flex items-center gap-2">
                <AppButton type="button" size="sm" onClick={() => uploadInputRef.current?.click()}>
                  选择文件
                </AppButton>
                <AppButton
                  type="button"
                  size="sm"
                  variant="success"
                  loading={uploadingFiles}
                  loadingText="Uploading..."
                  disabled={!effectiveBatchScope.trim() || selectedUploadFiles.length === 0}
                  onClick={async () => {
                    setUploadingFiles(true);
                    try {
                      await props.onUploadFiles({
                        scope: effectiveBatchScope,
                        files: selectedUploadFiles,
                        tags: batchUploadTags
                          .split(",")
                          .map((item) => item.trim())
                          .filter((item) => item.length > 0),
                      });
                      setSelectedUploadFiles([]);
                      setBatchUploadTags("");
                      if (uploadInputRef.current) {
                        uploadInputRef.current.value = "";
                      }
                    } finally {
                      setUploadingFiles(false);
                    }
                  }}
                >
                  上传文件
                </AppButton>
              </div>
            </div>
          </div>
        </aside>

        <section ref={graphViewportRef} className="relative h-full min-h-0 w-full border-r border-zinc-200 dark:border-zinc-700">
          {props.loading ? (
            <div className="h-full flex items-center justify-center text-sm text-zinc-500">Loading...</div>
          ) : viewMode === "graph" ? (
              <div
                className="relative h-full w-full overflow-hidden"
                style={{
                  background:
                    "radial-gradient(circle at 20% 20%, rgba(219,234,254,0.7), transparent 28%), radial-gradient(circle at 80% 18%, rgba(191,219,254,0.45), transparent 24%), linear-gradient(180deg, #ffffff 0%, #f8fafc 48%, #eff6ff 100%)",
                }}
              >
                <div className="absolute inset-0 opacity-40" style={{ backgroundImage: "linear-gradient(rgba(148,163,184,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.08) 1px, transparent 1px)", backgroundSize: "32px 32px" }} />
                <div className="absolute top-3 left-3 z-10 w-[220px] rounded-2xl border border-slate-200/80 bg-white/88 p-3 text-[11px] text-slate-600 shadow-lg backdrop-blur">
                  <div className="font-medium text-slate-900">Graph Filters</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {([
                      ["hierarchy", "Hierarchy"],
                      ["tag", "Tag"],
                      ["source", "Source"],
                      ["similar", "Similar"],
                    ] as Array<[ForceGraphLinkData["relationType"], string]>).map(([key, label]) => (
                      <label key={key} className="flex items-center gap-1 text-slate-600">
                        <input
                          type="checkbox"
                          checked={relationFilters[key]}
                          onChange={(e) => setRelationFilters((prev) => ({ ...prev, [key]: e.target.checked }))}
                        />
                        {label}
                      </label>
                    ))}
                  </div>
                  <div className="mt-3 space-y-1">
                    <div><span className={`mr-1 inline-block h-2 w-2 rounded-full ${ragGraphTheme.legend.scope}`} /> scope</div>
                    <div><span className={`mr-1 inline-block h-2 w-2 rounded-full ${ragGraphTheme.legend.document}`} /> document</div>
                    <div><span className={`mr-1 inline-block h-2 w-2 rounded-full ${ragGraphTheme.legend.chunk}`} /> chunk</div>
                    <div><span className={`mr-1 inline-block h-[2px] w-4 align-middle ${ragGraphTheme.legend.tag}`} /> shared tag</div>
                    <div><span className={`mr-1 inline-block h-[2px] w-4 align-middle ${ragGraphTheme.legend.source}`} /> shared source</div>
                    <div><span className={`mr-1 inline-block h-[2px] w-4 align-middle ${ragGraphTheme.legend.similar}`} /> similar content</div>
                  </div>
                </div>
                <div className="absolute bottom-4 left-4 z-10 w-[220px] rounded-2xl border border-slate-200/80 bg-white/88 p-3 shadow-lg backdrop-blur">
                  <div className="text-[11px] text-slate-500">RAG Graph</div>
                  <div className="text-sm font-semibold text-slate-900">
                    {forceGraph.nodes.length} nodes · {forceGraph.links.length} edges
                  </div>
                  <div className="mt-3 border-t border-slate-200 pt-3">
                    <div className="mb-1 flex items-center justify-between text-[11px] text-slate-500">
                      <span>Node repulsion</span>
                      <span className="font-medium text-slate-700">{forceStrength}</span>
                    </div>
                    <input
                      type="range"
                      min="80"
                      max="340"
                      value={forceStrength}
                      onChange={(e) => setForceStrength(Number(e.target.value))}
                      className="w-full accent-blue-500"
                    />
                    <div className="mt-1 flex justify-between text-[10px] text-slate-400">
                      <span>compact</span>
                      <span>spread</span>
                    </div>
                  </div>
                </div>
                {hoveredGraphNodeId ? (
                  (() => {
                    const hovered = graphLayout.nodes.find((node) => node.id === hoveredGraphNodeId);
                    if (!hovered) return null;
                    return (
                      <div className="absolute top-3 right-3 z-10 max-w-[260px] rounded-2xl border border-slate-200/80 bg-white/92 p-3 shadow-lg backdrop-blur">
                        <div className="text-sm font-semibold text-slate-900">{truncateLabel(hovered.name, 42)}</div>
                        <div className="mt-1 flex items-center gap-2 text-[11px] text-slate-500">
                          <span
                            className="rounded-full px-2 py-0.5 font-medium"
                            style={{ backgroundColor: `${hovered.color}20`, color: hovered.color }}
                          >
                            {pickNodeTypeLabel(hovered.type)}
                          </span>
                          <span>{hovered.id}</span>
                        </div>
                        <div className="mt-2 text-[11px] text-slate-400">
                          {hovered.type === "document" ? "Click to inspect and edit this document." : "Click to inspect metadata."}
                        </div>
                      </div>
                    );
                  })()
                ) : null}
                <svg width={effectiveGraphWidth} height={effectiveGraphHeight} className="block h-full w-full">
                  <defs>
                    <radialGradient id="graphGlow" cx="50%" cy="50%" r="75%">
                      <stop offset="0%" stopColor={ragGraphTheme.glow} stopOpacity="0.18" />
                      <stop offset="100%" stopColor={ragGraphTheme.background} stopOpacity="0" />
                    </radialGradient>
                  </defs>
                  <rect width={effectiveGraphWidth} height={effectiveGraphHeight} fill={ragGraphTheme.background} />
                  <rect width={effectiveGraphWidth} height={effectiveGraphHeight} fill="url(#graphGlow)" />
                  <g>
                    {graphLayout.links.map((link) => {
                      const source = resolveNodePosition(link.source);
                      const target = resolveNodePosition(link.target);
                      if (!source || !target) return null;
                      return (
                        <line
                          key={link.id}
                          x1={source.x ?? 0}
                          y1={source.y ?? 0}
                          x2={target.x ?? 0}
                          y2={target.y ?? 0}
                          stroke={link.color.replace(/[\d.]+\)$/u, `${link.opacity})`)}
                          strokeWidth={link.width}
                          strokeDasharray={link.relationType === "hierarchy" ? undefined : link.relationType === "similar" ? "5 6" : "3 5"}
                          strokeLinecap="round"
                        />
                      );
                    })}
                    {graphLayout.nodes.map((node) => {
                      const isSelected = node.id === selectedGraphNodeId;
                      const isHovered = node.id === hoveredGraphNodeId;
                      const isNeighbor = forceGraph.neighborIds.has(node.id);
                      const showLabel = isSelected || isHovered || node.type !== "chunk" || (selectedGraphNodeId !== null && isNeighbor);
                      const outerRadius = isSelected ? node.ring + 3 : isHovered ? node.ring + 1.5 : node.ring;
                      const coreRadius = isSelected ? node.inner + 1 : node.inner;
                      return (
                        <g
                          key={node.id}
                          transform={`translate(${node.x ?? 0}, ${node.y ?? 0})`}
                          className="cursor-pointer"
                          onMouseEnter={() => setHoveredGraphNodeId(node.id)}
                          onMouseLeave={() => setHoveredGraphNodeId((current) => (current === node.id ? null : current))}
                          onClick={() => selectGraphNode(node)}
                        >
                          <circle
                            r={outerRadius}
                            fill={`${node.color}${node.type === "scope" ? "26" : "20"}`}
                            fillOpacity={node.opacity}
                            stroke={node.color}
                            strokeWidth={isSelected ? 3 : 2}
                          />
                          {(isSelected || isHovered) && (
                            <circle
                              r={outerRadius + 5}
                              fill="none"
                              stroke={`${node.color}35`}
                              strokeWidth={2}
                            />
                          )}
                          <text
                            y={-outerRadius - 8}
                            textAnchor="middle"
                            fontSize={showLabel ? 11 : 9}
                            fontWeight={isSelected ? 600 : showLabel ? 500 : 400}
                            fill="#334155"
                            opacity={showLabel ? Math.max(node.opacity, 0.96) : node.opacity * 0.2}
                          >
                            {truncateLabel(node.name)}
                          </text>
                          <circle
                            r={isSelected ? node.val + 1.5 : node.val}
                            fill="white"
                            fillOpacity={Math.max(node.opacity * 0.95, 0.28)}
                            stroke="rgba(255,255,255,0.9)"
                            strokeWidth={1}
                          />
                          <circle
                            r={coreRadius}
                            fill={node.color}
                            fillOpacity={Math.max(node.opacity, 0.3)}
                          />
                          <text
                            y={outerRadius + 14}
                            textAnchor="middle"
                            fontSize={10}
                            fontWeight={500}
                            fill="#64748b"
                            opacity={showLabel ? Math.max(node.opacity, 0.9) : 0}
                          >
                            {pickNodeTypeLabel(node.type)}
                          </text>
                        </g>
                      );
                    })}
                  </g>
                </svg>
              </div>
          ) : (
            <div className="relative h-full w-full bg-[#f7f9fc]">
              <div className="absolute left-3 top-3 z-10 w-[220px] rounded-2xl border border-slate-200/80 bg-white/92 p-3 text-[11px] text-slate-600 shadow-lg backdrop-blur">
                <div className="font-medium text-slate-900">Flow Editor</div>
                <div className="mt-1 text-slate-500">Flowise-style node canvas over the current RAG hierarchy.</div>
                <div className="mt-3 space-y-1">
                  <div><span className="mr-1 inline-block h-2 w-2 rounded-full bg-[#ff6b6b]" /> scope source</div>
                  <div><span className="mr-1 inline-block h-2 w-2 rounded-full bg-[#4ecdc4]" /> document card</div>
                  <div><span className="mr-1 inline-block h-2 w-2 rounded-full bg-[#3b82f6]" /> chunk segment</div>
                </div>
              </div>
              <div className="absolute bottom-3 left-3 z-10 rounded-2xl border border-slate-200/80 bg-white/92 px-3 py-2 text-[11px] text-slate-500 shadow-lg backdrop-blur">
                {flow.nodes.length} nodes · {flow.edges.length} connections
              </div>
              <ReactFlow
                nodes={flow.nodes}
                edges={flow.edges}
                nodeTypes={flowNodeTypes}
                edgeTypes={{ flowEditorEdge: FlowEditorEdge }}
                fitView
                minZoom={0.35}
                maxZoom={1.7}
                nodesDraggable={false}
                elementsSelectable
                onNodeClick={(_, node) => {
                  setSelectedGraphNodeId(node.id);
                  setSelectedNode(node.data.meta);
                  if (node.id.startsWith("document:")) {
                    const documentId = String(node.data.meta.documentId ?? "");
                    setSelectedDocumentId(documentId);
                    setSelectedDocumentDraft({
                      title: String(node.data.meta.title ?? ""),
                      scope: String(node.data.meta.scope ?? ""),
                      source: String(node.data.meta.source ?? ""),
                      tags: Array.isArray(node.data.meta.tags) ? node.data.meta.tags.map((x) => String(x)).join(", ") : "",
                      content: String(node.data.meta.content ?? ""),
                    });
                  } else {
                    setSelectedDocumentId("");
                    setSelectedDocumentDraft(null);
                  }
                }}
              >
                <MiniMap
                  pannable
                  zoomable
                  nodeColor={(node) => String((node.data as FlowEditorNodeData | undefined)?.accent ?? "#94a3b8")}
                  maskColor="rgba(148,163,184,0.14)"
                  style={{ backgroundColor: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 14 }}
                />
                <Controls style={{ backgroundColor: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 14 }} />
                <Background gap={20} size={1.2} color="#dbe3ef" />
              </ReactFlow>
            </div>
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
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm font-medium">Documents</div>
              {selectedDocumentId ? (
                <AppButton
                  type="button"
                  size="xs"
                  variant="danger"
                  loading={deletingDocument}
                  loadingText="Deleting..."
                  onClick={() => void handleDeleteSelectedDocument()}
                >
                  删除选中
                </AppButton>
              ) : null}
            </div>
            <div className="mt-2 space-y-2">
              {props.documents.map((doc) => (
                <div
                  key={doc.documentId}
                  className={`rounded border px-2 py-2 ${
                    selectedDocumentId === doc.documentId
                      ? "border-zinc-500 bg-zinc-100 dark:border-zinc-500 dark:bg-zinc-800/80"
                      : "border-zinc-200 dark:border-zinc-700"
                  }`}
                >
                  <button
                    type="button"
                    className="w-full text-left text-xs"
                    onClick={() => {
                      setSelectedGraphNodeId(`document:${doc.documentId}`);
                      setSelectedNode(buildDocumentMeta(doc));
                      setSelectedDocumentId(doc.documentId);
                      setSelectedDocumentDraft(buildDocumentDraft(doc));
                    }}
                  >
                    <div className="font-medium">{doc.title}</div>
                    <div className="text-zinc-500 mt-1">{doc.scope}</div>
                  </button>
                  <div className="mt-2 flex items-center justify-end">
                    <AppButton
                      type="button"
                      size="xs"
                      variant="danger"
                      loading={deletingDocument && deletingDocumentId === doc.documentId}
                      loadingText="Deleting..."
                      onClick={() => {
                        void handleDeleteDocument(doc);
                      }}
                    >
                      删除
                    </AppButton>
                  </div>
                </div>
              ))}
              {props.documents.length === 0 ? (
                <div className="text-xs text-zinc-500">No documents in current scope.</div>
              ) : null}
            </div>
          </div>

          {selectedDocumentId ? (
            <div className="mt-4 border-t border-zinc-200 dark:border-zinc-700 pt-3">
              <div className="text-sm font-medium">Edit Document</div>
              <BaseForm<DocumentFormValues>
                initialValues={selectedDocumentDraft ?? { scope: "", title: "", source: "", tags: "", content: "" }}
                validationSchema={documentSchema}
                onSubmit={async (values) => {
                  await props.onUpdateDocument({
                    documentId: selectedDocumentId,
                    scope: values.scope.trim(),
                    title: values.title.trim(),
                    content: values.content.trim(),
                    source: values.source.trim(),
                    tags: parseTags(values.tags),
                  });
                  setSelectedDocumentDraft({
                    scope: values.scope.trim(),
                    title: values.title.trim(),
                    source: values.source.trim(),
                    tags: values.tags,
                    content: values.content.trim(),
                  });
                }}
                enableReinitialize
                className="mt-2 space-y-2"
              >
                {({ isSubmitting, isValid }) => (
                  <>
                    <BaseSelect name="scope" className="text-xs">
                      <option value="">选择 scope</option>
                      {scopeOptions.map((scope) => (
                        <option key={scope} value={scope}>
                          {scope}
                        </option>
                      ))}
                    </BaseSelect>
                    <BaseField name="title" placeholder="title" className="text-xs" />
                    <BaseField name="source" placeholder="source" className="text-xs" />
                    <BaseField name="tags" placeholder="tags comma separated" className="text-xs" />
                    <BaseTextarea name="content" className="text-xs" rows={8} />
                    <div className="flex items-center gap-2">
                      <AppButton type="submit" size="sm" variant="success" loading={isSubmitting} loadingText="Updating..." disabled={!isValid}>
                        Update
                      </AppButton>
                      <AppButton
                        type="button"
                        size="sm"
                        variant="danger"
                        loading={deletingDocument}
                        loadingText="Deleting..."
                        onClick={() => void handleDeleteSelectedDocument()}
                      >
                        Delete
                      </AppButton>
                    </div>
                  </>
                )}
              </BaseForm>
            </div>
          ) : null}
        </aside>
      </div>
    </AppModal>
  );
}
