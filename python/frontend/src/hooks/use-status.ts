import { useQuery } from "@tanstack/react-query";
import { fetchStatus } from "@/lib/api";

export function useStatus() {
  return useQuery({
    queryKey: ["status"],
    queryFn: fetchStatus,
    refetchInterval: 5000,
  });
}
