import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { StatsCards } from "../stats-cards";

const mockStatus = {
  total_files: 100,
  succeeded: 50,
  failed: 7,
  pending: 30,
  in_progress: 10,
  retry_pending: 3,
  success_rate: 50.0,
};

describe("StatsCards", () => {
  it("renders all five stat cards", () => {
    render(<StatsCards status={mockStatus} />);
    expect(screen.getByText("Succeeded")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.getByText("In Progress")).toBeInTheDocument();
    expect(screen.getByText("Retry Pending")).toBeInTheDocument();
  });

  it("renders correct values", () => {
    render(<StatsCards status={mockStatus} />);
    expect(screen.getByText("50")).toBeInTheDocument(); // succeeded
    expect(screen.getByText("7")).toBeInTheDocument();  // failed
    expect(screen.getByText("30")).toBeInTheDocument(); // pending
    expect(screen.getByText("10")).toBeInTheDocument(); // in_progress
    expect(screen.getByText("3")).toBeInTheDocument();  // retry_pending
  });
});
