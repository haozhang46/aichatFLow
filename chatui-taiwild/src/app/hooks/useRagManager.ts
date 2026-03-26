"use client";

import { useState } from "react";
import type { RagDocument, RagGraph } from "@/app/components/modalTypes";
import { apiDelete, apiPost } from "@/lib/api-client";
import { useApiSWR } from "@/lib/swr";

type AddRagDocumentPayload = {
  scope: string;
  title: string;
  content: string;
  source: string;
  tags: string[];
};

type UpdateRagDocumentPayload = {
  documentId: string;
  scope: string;
  title: string;
  content: string;
  source: string;
  tags: string[];
};

type BatchIngestPayload = {
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
};

type UploadRagFilesPayload = {
  scope: string;
  files: File[];
  tags: string[];
};

type Params = {
  tenantId: string;
};

type RagScopesResponse = { items?: string[] };
type RagDocumentsResponse = { items?: RagDocument[] };
type RagGraphResponse = { graph?: RagGraph | null };

export function useRagManager({ tenantId }: Params) {
  const [mutationLoading, setMutationLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedScope, setSelectedScopeState] = useState("");
  const scopeQuery = selectedScope.trim();

  const scopesSWR = useApiSWR<RagScopesResponse>(tenantId ? "/v1/rag/scopes" : null, {
    tenantId,
  });
  const documentsSWR = useApiSWR<RagDocumentsResponse>(tenantId ? "/v1/rag/documents" : null, {
    tenantId,
    scope: scopeQuery || undefined,
  });
  const graphSWR = useApiSWR<RagGraphResponse>(tenantId ? "/v1/rag/graph" : null, {
    tenantId,
    scope: scopeQuery || undefined,
  });

  const scopes = Array.isArray(scopesSWR.data?.items) ? scopesSWR.data.items.map((x) => String(x)) : [];
  const documents = Array.isArray(documentsSWR.data?.items) ? documentsSWR.data.items : [];
  const graph = (graphSWR.data?.graph as RagGraph | null | undefined) ?? { nodes: [], edges: [] };
  const loading = mutationLoading || scopesSWR.isLoading || documentsSWR.isLoading || graphSWR.isLoading;

  async function refreshCurrent() {
    await Promise.all([scopesSWR.mutate(), documentsSWR.mutate(), graphSWR.mutate()]);
  }

  async function load(scope = selectedScope) {
    setError(null);
    const nextScope = scope.trim();
    if (nextScope !== scopeQuery) {
      setSelectedScopeState(nextScope);
      return;
    }
    await refreshCurrent();
  }

  async function createScope(scope: string) {
    const nextScope = scope.trim();
    if (!nextScope) return;
    setError(null);
    setMutationLoading(true);
    try {
      await apiPost("/v1/rag/scopes", { tenantId, scope: nextScope });
      setSelectedScopeState(nextScope);
      await Promise.all([scopesSWR.mutate(), documentsSWR.mutate(), graphSWR.mutate()]);
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      throw e;
    } finally {
      setMutationLoading(false);
    }
  }

  async function addDocument(payload: AddRagDocumentPayload) {
    setError(null);
    setMutationLoading(true);
    try {
      await apiPost("/v1/rag/documents", { tenantId, ...payload });
      const nextScope = payload.scope.trim();
      setSelectedScopeState(nextScope);
      await Promise.all([documentsSWR.mutate(), graphSWR.mutate(), scopesSWR.mutate()]);
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      throw e;
    } finally {
      setMutationLoading(false);
    }
  }

  async function updateDocument(payload: UpdateRagDocumentPayload) {
    setError(null);
    setMutationLoading(true);
    try {
      await apiPost("/v1/rag/documents", { tenantId, ...payload });
      const nextScope = payload.scope.trim();
      setSelectedScopeState(nextScope);
      await Promise.all([documentsSWR.mutate(), graphSWR.mutate(), scopesSWR.mutate()]);
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      throw e;
    } finally {
      setMutationLoading(false);
    }
  }

  async function deleteDocument(documentId: string) {
    setError(null);
    setMutationLoading(true);
    try {
      await apiDelete(`/v1/rag/documents/${encodeURIComponent(documentId)}`, { tenantId });
      await Promise.all([documentsSWR.mutate(), graphSWR.mutate(), scopesSWR.mutate()]);
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      throw e;
    } finally {
      setMutationLoading(false);
    }
  }

  async function batchIngest(payload: BatchIngestPayload) {
    setError(null);
    setMutationLoading(true);
    try {
      await apiPost("/v1/rag/documents/batch", { tenantId, scope: payload.scope, items: payload.items });
      const nextScope = payload.scope.trim();
      setSelectedScopeState(nextScope);
      await Promise.all([documentsSWR.mutate(), graphSWR.mutate(), scopesSWR.mutate()]);
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      throw e;
    } finally {
      setMutationLoading(false);
    }
  }

  async function uploadFiles(payload: UploadRagFilesPayload) {
    setError(null);
    setMutationLoading(true);
    const form = new FormData();
    form.set("tenantId", tenantId);
    form.set("scope", payload.scope);
    form.set("tags", payload.tags.join(","));
    for (const file of payload.files) {
      form.append("files", file, file.name);
    }
    try {
      await apiPost("/v1/rag/documents/upload", form);
      const nextScope = payload.scope.trim();
      setSelectedScopeState(nextScope);
      await Promise.all([documentsSWR.mutate(), graphSWR.mutate(), scopesSWR.mutate()]);
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      throw e;
    } finally {
      setMutationLoading(false);
    }
  }

  function setSelectedScope(value: string) {
    setSelectedScopeState(value);
  }

  return {
    loading,
    error,
    scopes,
    documents,
    graph,
    selectedScope,
    setSelectedScope,
    load,
    createScope,
    addDocument,
    updateDocument,
    deleteDocument,
    batchIngest,
    uploadFiles,
  };
}
