import { useNavigate } from "@tanstack/react-router";
import { EntriesTable } from "@/components/entries-table";
import type { EntrySummary } from "@/lib/types";

export function EntriesPage() {
  const navigate = useNavigate();

  const handleSelect = (entry: EntrySummary) => {
    navigate({ to: "/entries/$entryId", params: { entryId: entry.id } });
  };

  return <EntriesTable onSelect={handleSelect} />;
}
