import { useNavigate, useParams } from "@tanstack/react-router";
import { EntryDetail } from "@/components/entry-detail";

export function EntryDetailPage() {
  const { entryId } = useParams({ from: "/entries/$entryId" });
  const navigate = useNavigate();

  return (
    <EntryDetail
      entryId={entryId}
      onBack={() => navigate({ to: "/entries" })}
    />
  );
}
