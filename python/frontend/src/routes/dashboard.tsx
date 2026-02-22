import { StatsCards } from "@/components/stats-cards";
import { ProgressBar } from "@/components/progress-bar";
import { LogStream } from "@/components/log-stream";
import { useStatus } from "@/hooks/use-status";

export function DashboardPage() {
  const { data: status, isLoading } = useStatus();

  return (
    <>
      {isLoading || !status ? (
        <div className="py-12 text-center text-text-muted">Loading dashboard...</div>
      ) : (
        <>
          <StatsCards status={status} />
          <ProgressBar
            successRate={status.success_rate}
            total={status.total_files}
            succeeded={status.succeeded}
          />
        </>
      )}
      <LogStream />
    </>
  );
}
