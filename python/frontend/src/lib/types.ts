export interface HealthResponse {
  status: string;
  version: string;
  llm_provider: string;
  llm_model: string;
  llm_healthy: boolean;
}

export interface StatusResponse {
  total_files: number;
  succeeded: number;
  failed: number;
  pending: number;
  in_progress: number;
  retry_pending: number;
  success_rate: number;
}

export interface EntryListResponse {
  total: number;
  entries: EntrySummary[];
}

export interface EntrySummary {
  id: string;
  name: string;
  status: string;
  protocol: string;
  retry_count: number;
  last_error: string | null;
  commit_hash: string | null;
  updated_at: string;
}

export interface EntryDetail extends EntrySummary {
  legacy_config: string;
  new_config: string | null;
  deployment_id: string | null;
  source_path: string | null;
  destination_path: string | null;
  created_at: string;
}

export interface ReportResponse {
  generated_at: string;
  total_files: number;
  succeeded: number;
  failed: number;
  pending: number;
  in_progress: number;
  retry_pending: number;
  success_rate: number;
  summary: string;
}

export interface ConfigResponse {
  agent: {
    batch_size: number;
    max_retries_per_file: number;
    poll_interval_seconds: number;
  };
  llm: {
    provider: string;
  };
  deployment: {
    provider: string;
  };
  monitoring: {
    provider: string;
  };
}

export interface LogMessage {
  timestamp: string;
  level: string;
  event: string;
  [key: string]: unknown;
}
