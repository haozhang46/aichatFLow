"use client";

import useSWR, { type SWRConfiguration } from "swr";
import { apiGet, type ApiQuery } from "@/lib/api-client";

type ApiSWRKey = [string, ApiQuery | undefined];

async function apiSWRFetcher<T>([path, query]: ApiSWRKey) {
  return apiGet<T>(path, query);
}

export function useApiSWR<T>(
  path: string | null,
  query?: ApiQuery,
  config?: SWRConfiguration<T, Error>
) {
  const key = path ? ([path, query] as ApiSWRKey) : null;
  return useSWR<T, Error, ApiSWRKey | null>(key, apiSWRFetcher, {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
    ...config,
  });
}
