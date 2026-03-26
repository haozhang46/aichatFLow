"use client";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

type QueryValue = string | number | boolean | null | undefined;

export type ApiQuery = Record<string, QueryValue>;

function buildQueryString(query?: ApiQuery) {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value == null || value === "") continue;
    params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

export function buildApiUrl(path: string, query?: ApiQuery) {
  return `${API_BASE_URL}${path}${buildQueryString(query)}`;
}

export async function apiFetch<T = unknown>(path: string, init?: RequestInit, query?: ApiQuery): Promise<T> {
  const res = await fetch(buildApiUrl(path, query), init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const message =
      typeof (data as { detail?: unknown })?.detail === "string"
        ? (data as { detail: string }).detail
        : `Request failed: ${path}`;
    throw new Error(message);
  }
  return data as T;
}

export async function apiGet<T = unknown>(path: string, query?: ApiQuery): Promise<T> {
  return apiFetch<T>(path, undefined, query);
}

export async function apiPost<T = unknown>(path: string, body?: unknown, query?: ApiQuery): Promise<T> {
  return apiFetch<T>(
    path,
    {
      method: "POST",
      headers: body instanceof FormData ? undefined : { "Content-Type": "application/json" },
      body: body instanceof FormData ? body : body == null ? undefined : JSON.stringify(body),
    },
    query
  );
}

export async function apiDelete<T = unknown>(path: string, query?: ApiQuery): Promise<T> {
  return apiFetch<T>(
    path,
    {
      method: "DELETE",
    },
    query
  );
}

export async function apiPut<T = unknown>(path: string, body?: unknown, query?: ApiQuery): Promise<T> {
  return apiFetch<T>(
    path,
    {
      method: "PUT",
      headers: body instanceof FormData ? undefined : { "Content-Type": "application/json" },
      body: body instanceof FormData ? body : body == null ? undefined : JSON.stringify(body),
    },
    query
  );
}
