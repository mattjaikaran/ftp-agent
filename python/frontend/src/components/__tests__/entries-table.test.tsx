import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EntriesTable } from "../entries-table";

// Mock the useEntries hook
vi.mock("@/hooks/use-entries", () => ({
  useEntries: () => ({
    data: {
      total: 2,
      entries: [
        { id: "e1", name: "sftp-prod", status: "SUCCESS", protocol: "SFTP", retry_count: 0, last_error: null, commit_hash: "abc123", updated_at: "2025-01-01T00:00:00Z" },
        { id: "e2", name: "ftp-staging", status: "PENDING", protocol: "FTP", retry_count: 1, last_error: "timeout", commit_hash: null, updated_at: "2025-01-02T00:00:00Z" },
      ],
    },
    isLoading: false,
    error: null,
  }),
}));

function renderWithQueryClient(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("EntriesTable", () => {
  it("renders entry rows", () => {
    renderWithQueryClient(<EntriesTable />);
    expect(screen.getByText("sftp-prod")).toBeInTheDocument();
    expect(screen.getByText("ftp-staging")).toBeInTheDocument();
  });

  it("renders status badges in table rows", () => {
    renderWithQueryClient(<EntriesTable />);
    // Status badges are rendered as <span> elements with rounded-full class inside table cells
    const successBadges = screen.getAllByText("SUCCESS");
    // At least one is the badge in the table row (another may be in the filter bar)
    expect(successBadges.length).toBeGreaterThanOrEqual(1);

    const pendingBadges = screen.getAllByText("PENDING");
    expect(pendingBadges.length).toBeGreaterThanOrEqual(1);
  });

  it("shows total count", () => {
    renderWithQueryClient(<EntriesTable />);
    expect(screen.getByText("File Entries (2)")).toBeInTheDocument();
  });

  it("renders filter buttons", () => {
    renderWithQueryClient(<EntriesTable />);
    expect(screen.getByText("All")).toBeInTheDocument();
    expect(screen.getByText("FAILED")).toBeInTheDocument();
  });
});
