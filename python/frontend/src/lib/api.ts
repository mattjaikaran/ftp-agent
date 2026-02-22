import axios from "axios";
import type {
  HealthResponse,
  StatusResponse,
  EntryListResponse,
  EntryDetail,
  ReportResponse,
  ConfigResponse,
} from "./types";

const API_KEY_STORAGE = "ftp-agent-api-key";

const api = axios.create({
  baseURL: "/api",
  timeout: 15000,
});

// Auth interceptor — adds Bearer token from localStorage if present
api.interceptors.request.use((config) => {
  const key = localStorage.getItem(API_KEY_STORAGE);
  if (key) {
    config.headers.Authorization = `Bearer ${key}`;
  }
  return config;
});

export async function fetchHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>("/health");
  return data;
}

export async function fetchStatus(): Promise<StatusResponse> {
  const { data } = await api.get<StatusResponse>("/status");
  return data;
}

export async function fetchEntries(
  statusFilter?: string,
  limit = 100,
  offset = 0,
  search?: string,
): Promise<EntryListResponse> {
  const params: Record<string, string | number> = { limit, offset };
  if (statusFilter) params.status_filter = statusFilter;
  if (search) params.search = search;
  const { data } = await api.get<EntryListResponse>("/entries", { params });
  return data;
}

export async function fetchEntry(id: string): Promise<EntryDetail> {
  const { data } = await api.get<EntryDetail>(`/entries/${id}`);
  return data;
}

export async function fetchReport(): Promise<ReportResponse> {
  const { data } = await api.get<ReportResponse>("/report");
  return data;
}

export async function fetchConfig(): Promise<ConfigResponse> {
  const { data } = await api.get<ConfigResponse>("/config");
  return data;
}

export async function triggerRun(dryRun = true): Promise<{ status: string; message: string }> {
  const { data } = await api.post<{ status: string; message: string }>("/run", null, {
    params: { dry_run: dryRun },
  });
  return data;
}

export async function stopRun(): Promise<{ status: string; message: string }> {
  const { data } = await api.post<{ status: string; message: string }>("/run/stop");
  return data;
}
