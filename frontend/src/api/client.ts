export type Run = {
  run_id: string;
  workflow?: string;
  status?: string;
  started_at?: string;
  finished_at?: string;
  duration_ms?: number;
  report_path?: string;
  report?: string;
  summary?: Record<string, number>;
};

export type TimelineEvent = {
  event_id?: number;
  timestamp?: string;
  run_id?: string;
  workflow?: string;
  event?: string;
  status?: string;
  phase?: string;
  phase_id?: string;
  step_id?: string;
  record_id?: string;
  action_type?: string;
  failure_kind?: string;
  evidence_bundle?: string;
  message?: string;
};

export type RecordResult = {
  run_id?: string;
  workflow?: string;
  record_id?: string;
  row_number?: number;
  status?: string;
  failed_step?: string;
  failure_kind?: string;
  safe_retry?: string;
  evidence_bundle_path?: string;
};

export type Failure = {
  run_id?: string;
  workflow?: string;
  phase_id?: string;
  step_id?: string;
  record_id?: string;
  action_type?: string;
  status?: string;
  failure_kind?: string;
  evidence_bundle_path?: string;
  repair_packet_path?: string;
  message?: string;
};

export type WorkflowGraph = {
  workflow: string;
  schema_version: number;
  phases: Array<{
    id: string;
    name?: string;
    steps: Array<{
      id: string;
      action_type?: string;
      success_checks: string[];
      side_effect?: string;
      retryable?: boolean;
      selector_quality?: string;
      human_gate?: boolean;
      warnings?: string[];
    }>;
  }>;
  summary: Record<string, number>;
};

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  listRuns: () => getJson<{ runs: Run[] }>("/api/runs"),
  getRun: (runId: string) => getJson<Record<string, unknown>>(`/api/runs/${encodeURIComponent(runId)}`),
  getTimeline: (runId: string) => getJson<{ events: TimelineEvent[] }>(`/api/runs/${encodeURIComponent(runId)}/timeline`),
  pollEvents: (runId: string, afterId = 0) =>
    getJson<{ events: TimelineEvent[] }>(`/api/runs/${encodeURIComponent(runId)}/events?after_id=${afterId}`),
  getRecords: () => getJson<{ records: RecordResult[] }>("/api/records"),
  getFailures: () => getJson<{ failures: Failure[] }>("/api/failures"),
  getSelectors: () => getJson<{ selector_failures: Failure[] }>("/api/selector-failures"),
  getRepairPackets: () => getJson<{ repair_packets: Failure[] }>("/api/repair-packets"),
  getSummary: () => getJson<Record<string, unknown>>("/api/observability/summary"),
  getBuilders: () => getJson<{ sessions: Array<Record<string, unknown>> }>("/api/builder/sessions"),
  getWorkflowGraph: (path: string) => getJson<WorkflowGraph>(`/api/workflows/${path}/graph`),
};
