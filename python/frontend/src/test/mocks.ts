import { http, HttpResponse } from "msw";

export const handlers = [
  http.get("/api/health", () =>
    HttpResponse.json({
      status: "ok",
      version: "2.0.0",
      llm_provider: "minimax",
      llm_model: "MiniMax-M2.5",
      llm_healthy: true,
    })
  ),
  http.get("/api/status", () =>
    HttpResponse.json({
      total_files: 100,
      succeeded: 50,
      failed: 5,
      pending: 30,
      in_progress: 10,
      retry_pending: 5,
      success_rate: 50.0,
    })
  ),
  http.get("/api/entries", () =>
    HttpResponse.json({
      total: 2,
      entries: [
        { id: "e1", name: "sftp-prod", status: "SUCCESS", protocol: "SFTP", retry_count: 0, last_error: null, commit_hash: "abc123", updated_at: "2025-01-01T00:00:00Z" },
        { id: "e2", name: "ftp-staging", status: "PENDING", protocol: "FTP", retry_count: 1, last_error: "timeout", commit_hash: null, updated_at: "2025-01-02T00:00:00Z" },
      ],
    })
  ),
  http.get("/api/config", () =>
    HttpResponse.json({
      agent: { batch_size: 10, max_retries_per_file: 3, poll_interval_seconds: 30, schedule_interval_hours: 0 },
      llm: { provider: "minimax" },
      deployment: { provider: "stub" },
      monitoring: { provider: "stub" },
    })
  ),
];
