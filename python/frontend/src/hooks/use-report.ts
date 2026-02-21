import { useQuery } from "@tanstack/react-query";
import { fetchReport } from "@/lib/api";

export function useReport() {
  return useQuery({
    queryKey: ["report"],
    queryFn: fetchReport,
    refetchInterval: 15000,
  });
}
