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
  duration_ms?: number;
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
  safe_retry?: boolean | string;
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
  safe_retry?: boolean | string;
  recommended_next_action?: string;
  evidence_bundle_path?: string;
  repair_packet_path?: string;
  selector_evidence_path?: string;
  message?: string;
};

export type RunStep = Failure & {
  duration_ms?: number;
  side_effect?: string;
  retryable?: boolean | number;
  selector_quality?: string;
};

export type DesktopEvidence = Failure & {
  id?: number;
  screenshot_path?: string;
  gif_path?: string;
  recording_path?: string;
  video_path?: string;
  dom_snapshot_path?: string;
  uia_snapshot_path?: string;
  win32_snapshot_path?: string;
  ocr_artifact_path?: string;
  api_preview_path?: string;
  logs_path?: string;
  desktop_backend?: string;
  selector_quality?: string;
  verification_method?: string;
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

export type RunDetail = {
  manifest?: Run & Record<string, unknown>;
  timeline?: TimelineEvent[];
  records?: RecordResult[];
  report_html?: string;
  failure_report?: Record<string, unknown>;
  repair_packet?: Record<string, unknown>;
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
  getRun: (runId: string) => getJson<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`),
  getTimeline: (runId: string) => getJson<{ events: TimelineEvent[] }>(`/api/runs/${encodeURIComponent(runId)}/timeline`),
  pollEvents: (runId: string, afterId = 0) =>
    getJson<{ events: TimelineEvent[] }>(`/api/runs/${encodeURIComponent(runId)}/events?after_id=${afterId}`),
  getRunSteps: (runId: string) => getJson<{ steps: RunStep[] }>(`/api/runs/${encodeURIComponent(runId)}/steps`),
  getRunRecords: (runId: string) => getJson<{ records: RecordResult[] }>(`/api/runs/${encodeURIComponent(runId)}/records`),
  getRunFailures: (runId: string) => getJson<{ failures: Failure[] }>(`/api/runs/${encodeURIComponent(runId)}/failures`),
  getDesktopEvidence: (runId: string) => getJson<{ evidence: DesktopEvidence[] }>(`/api/desktop/evidence?run_id=${encodeURIComponent(runId)}`),
  getRecords: () => getJson<{ records: RecordResult[] }>("/api/records"),
  getFailures: () => getJson<{ failures: Failure[] }>("/api/failures"),
  getSelectors: () => getJson<{ selector_failures: Failure[] }>("/api/selector-failures"),
  getRepairPackets: () => getJson<{ repair_packets: Failure[] }>("/api/repair-packets"),
  getSummary: () => getJson<Record<string, unknown>>("/api/observability/summary"),
  getBuilders: () => getJson<{ sessions: Array<Record<string, unknown>> }>("/api/builder/sessions"),
  getWorkflowGraph: (path: string) => getJson<WorkflowGraph>(`/api/workflows/${path}/graph`),
};
