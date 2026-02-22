import { cn } from "@/lib/cn";
import { useHealth } from "@/hooks/use-health";
import { Brain } from "lucide-react";

export function LlmStatus() {
  const { data, isLoading } = useHealth();

  if (isLoading || !data) {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-bg-inset px-3 py-1.5 text-sm text-text-muted">
        <Brain className="h-4 w-4" />
        <span>Checking LLM...</span>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium",
        data.llm_healthy
          ? "bg-success-soft text-success"
          : "bg-danger-soft text-danger",
      )}
    >
      <Brain className="h-4 w-4" />
      <span>{data.llm_provider}</span>
      <span className="text-xs font-normal opacity-70">{data.llm_model}</span>
      <span
        className={cn(
          "inline-block h-2 w-2 rounded-full",
          data.llm_healthy ? "bg-success" : "bg-danger",
        )}
      />
    </div>
  );
}
