import { useQuery } from "@tanstack/react-query";
import { fetchEntries, fetchEntry } from "@/lib/api";

export function useEntries(statusFilter?: string, limit = 100, offset = 0) {
  return useQuery({
    queryKey: ["entries", statusFilter, limit, offset],
    queryFn: () => fetchEntries(statusFilter, limit, offset),
    refetchInterval: 10000,
  });
}

export function useEntry(id: string) {
  return useQuery({
    queryKey: ["entry", id],
    queryFn: () => fetchEntry(id),
    enabled: !!id,
  });
}
