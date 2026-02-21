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
}

function StatCard({ label, value, icon, color }: StatCardProps) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">{label}</p>
          <p className={cn("mt-1 text-3xl font-bold", color)}>{value}</p>
        </div>
        <div className={cn("rounded-lg p-3", color.replace("text-", "bg-") + "/10")}>
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
        icon={<CheckCircle className="h-6 w-6 text-green-600" />}
        color="text-green-600"
      />
      <StatCard
        label="Failed"
        value={status.failed}
        icon={<XCircle className="h-6 w-6 text-red-600" />}
        color="text-red-600"
      />
      <StatCard
        label="Pending"
        value={status.pending}
        icon={<Clock className="h-6 w-6 text-amber-600" />}
        color="text-amber-600"
      />
      <StatCard
        label="In Progress"
        value={status.in_progress}
        icon={<Loader2 className="h-6 w-6 text-blue-600" />}
        color="text-blue-600"
      />
      <StatCard
        label="Retry Pending"
        value={status.retry_pending}
        icon={<RotateCcw className="h-6 w-6 text-purple-600" />}
        color="text-purple-600"
      />
    </div>
  );
}
