import { cn } from "@/lib/cn";
import type { StatusResponse } from "@/lib/types";
import { CheckCircle, XCircle, Clock, Loader2, RotateCcw } from "lucide-react";

interface StatsCardsProps {
  status: StatusResponse;
}

interface StatCardProps {
  label: string;
  value: number;
  icon: React.ReactNode;
  color: string;
  bgColor: string;
}

function StatCard({ label, value, icon, color, bgColor }: StatCardProps) {
  return (
    <div className="rounded-xl border border-border bg-bg-card p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-text-muted">{label}</p>
          <p className={cn("mt-1 text-3xl font-bold", color)}>{value}</p>
        </div>
        <div className={cn("rounded-lg p-3", bgColor)}>
          {icon}
        </div>
      </div>
    </div>
  );
}

export function StatsCards({ status }: StatsCardsProps) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
      <StatCard
        label="Succeeded"
        value={status.succeeded}
        icon={<CheckCircle className="h-6 w-6 text-success" />}
        color="text-success"
        bgColor="bg-success-soft"
      />
      <StatCard
        label="Failed"
        value={status.failed}
        icon={<XCircle className="h-6 w-6 text-danger" />}
        color="text-danger"
        bgColor="bg-danger-soft"
      />
      <StatCard
        label="Pending"
        value={status.pending}
        icon={<Clock className="h-6 w-6 text-warning" />}
        color="text-warning"
        bgColor="bg-warning-soft"
      />
      <StatCard
        label="In Progress"
        value={status.in_progress}
        icon={<Loader2 className="h-6 w-6 text-info" />}
        color="text-info"
        bgColor="bg-info-soft"
      />
      <StatCard
        label="Retry Pending"
        value={status.retry_pending}
        icon={<RotateCcw className="h-6 w-6 text-purple-500 dark:text-purple-400" />}
        color="text-purple-500 dark:text-purple-400"
        bgColor="bg-purple-50 dark:bg-purple-950/40"
      />
    </div>
  );
}
