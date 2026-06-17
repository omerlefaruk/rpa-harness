import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  DesktopEvidence,
  Failure,
  RecordResult,
  Run,
  RunDetail,
  RunStep,
  TimelineEvent,
  WorkflowGraph,
} from "./api/client";

type Tab = "monitor" | "history" | "builder";

const tabs: Array<[Tab, string]> = [
  ["monitor", "Monitor"],
  ["history", "History"],
  ["builder", "Builder"],
];

type ProcessStep = {
  id: string;
  phase: string;
  status: string;
  actionType: string;
  proofCount: number;
  sideEffect: string;
  selectorQuality: string;
  durationMs?: number;
  failureKind?: string;
  message?: string;
};

type ProcessPhase = {
  id: string;
  name: string;
  steps: ProcessStep[];
};

type NarrativeItem = {
  id: string;
  title: string;
  body: string;
  meta: string;
  status: string;
  kind: string;
};

type EvidenceEntry = {
  label: string;
  path: string;
  kind: string;
};

function timelineKey(event: TimelineEvent): string {
  if (event.event_id !== undefined && event.event_id !== null) return String(event.event_id);
  return `${event.timestamp || ""}|${event.event || ""}|${event.step_id || ""}|${event.record_id || ""}|${event.message || ""}`;
}

function lastTimelineId(events: TimelineEvent[]): number {
  return events.reduce((max, event) => Math.max(max, Number(event.event_id || 0)), 0);
}

function mergeTimelineEvents(current: TimelineEvent[], incoming: TimelineEvent[]): TimelineEvent[] {
  const merged = new Map<string, TimelineEvent>();
  for (const event of current.concat(incoming)) {
    merged.set(timelineKey(event), event);
  }
  return Array.from(merged.values()).sort((left, right) => {
    const leftId = Number(left.event_id || 0);
    const rightId = Number(right.event_id || 0);
    if (leftId !== rightId) return leftId - rightId;
    return String(left.timestamp || "").localeCompare(String(right.timestamp || ""));
  });
}

export function App() {
  const [tab, setTab] = useState<Tab>("monitor");
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRun, setSelectedRun] = useState("");
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [runDetail, setRunDetail] = useState<RunDetail>({});
  const [records, setRecords] = useState<RecordResult[]>([]);
  const [runSteps, setRunSteps] = useState<RunStep[]>([]);
  const [runFailures, setRunFailures] = useState<Failure[]>([]);
  const [repairs, setRepairs] = useState<Failure[]>([]);
  const [desktopEvidence, setDesktopEvidence] = useState<DesktopEvidence[]>([]);
  const [summary, setSummary] = useState<Record<string, unknown>>({});
  const [builders, setBuilders] = useState<Array<Record<string, unknown>>>([]);
  const [graph, setGraph] = useState<WorkflowGraph | null>(null);
  const [error, setError] = useState("");
  const timelineLastId = useRef(0);

  const appendTimelineEvents = useCallback((events: TimelineEvent[]) => {
    if (!events.length) return;
    setTimeline((current) => {
      const next = mergeTimelineEvents(current, events);
      timelineLastId.current = lastTimelineId(next);
      return next.slice(-300);
    });
  }, []);

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    const timer = window.setInterval(async () => {
      try {
        const data = await api.listRuns();
        setRuns(data.runs);
        setSelectedRun((current) => {
          if (current && data.runs.some((run) => run.run_id === current)) return current;
          return data.runs[0]?.run_id || "";
        });
      } catch (err) {
        showError(err);
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    if (!selectedRun) {
      timelineLastId.current = 0;
      setTimeline([]);
      setRunDetail({});
      setRecords([]);
      setRunSteps([]);
      setRunFailures([]);
      setDesktopEvidence([]);
      setGraph(null);
      return;
    }

    const loadRunDetail = async () => {
      try {
        const detail = await api.getRun(selectedRun);
        const [stepData, recordData, failureData, evidenceData, repairData] = await Promise.all([
          api.getRunSteps(selectedRun),
          api.getRunRecords(selectedRun),
          api.getRunFailures(selectedRun),
          api.getDesktopEvidence(selectedRun),
          api.getRepairPackets(),
        ]);
        if (cancelled) return;
        setRunDetail(detail);
        setRunSteps(stepData.steps);
        setRecords(recordData.records.length ? recordData.records : detail.records || []);
        setRunFailures(failureData.failures);
        setDesktopEvidence(evidenceData.evidence);
        setRepairs(repairData.repair_packets);
        setTimeline((current) => {
          const rows = mergeTimelineEvents(current, detail.timeline || []);
          timelineLastId.current = lastTimelineId(rows);
          return rows.slice(-300);
        });
        const workflowPath = detail.manifest?.workflow_path;
        if (typeof workflowPath === "string" && workflowPath) {
          try {
            setGraph(await api.getWorkflowGraph(workflowPath));
          } catch {
            setGraph(null);
          }
        }
      } catch (err) {
        if (!cancelled) showError(err);
      }
    };

    loadRunDetail();
    timer = window.setInterval(loadRunDetail, 3000);
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearInterval(timer);
    };
  }, [selectedRun]);

  useEffect(() => {
    if (!selectedRun) return;
    let closed = false;
    let pollTimer: number | undefined;
    let source: EventSource | undefined;

    const poll = async () => {
      try {
        const data = await api.pollEvents(selectedRun, timelineLastId.current);
        appendTimelineEvents(data.events);
      } catch (err) {
        if (!closed) showError(err);
      }
    };

    const startPolling = () => {
      if (pollTimer !== undefined) return;
      pollTimer = window.setInterval(poll, 1500);
    };

    if ("EventSource" in window) {
      source = new EventSource(`/api/runs/${encodeURIComponent(selectedRun)}/events?stream=true&after_id=${timelineLastId.current}`);
      source.addEventListener("timeline", (message) => {
        try {
          appendTimelineEvents([JSON.parse((message as MessageEvent).data) as TimelineEvent]);
        } catch (err) {
          if (!closed) showError(err);
        }
      });
      source.onerror = () => {
        source?.close();
        startPolling();
      };
    } else {
      startPolling();
    }

    return () => {
      closed = true;
      source?.close();
      if (pollTimer !== undefined) window.clearInterval(pollTimer);
    };
  }, [selectedRun, appendTimelineEvents]);

  const selected = useMemo(
    () => runs.find((run) => run.run_id === selectedRun) || runs[0],
    [runs, selectedRun],
  );
  const selectedRunId = selected?.run_id || selectedRun;
  const selectedRepairs = useMemo(
    () => repairs.filter((repair) => !selectedRunId || repair.run_id === selectedRunId),
    [repairs, selectedRunId],
  );

  async function refresh() {
    setError("");
    try {
      const [runData, summaryData, builderData, repairData] = await Promise.all([
        api.listRuns(),
        api.getSummary(),
        api.getBuilders(),
        api.getRepairPackets(),
      ]);
      setRuns(runData.runs);
      setSelectedRun((current) => current || runData.runs[0]?.run_id || "");
      setSummary(summaryData);
      setBuilders(builderData.sessions);
      setRepairs(repairData.repair_packets);
    } catch (err) {
      showError(err);
    }
  }

  function showError(err: unknown) {
    setError(err instanceof Error ? err.message : String(err));
  }

  const title = tabs.find(([id]) => id === tab)?.[1] || "Monitor";

  return (
    <main className="consoleShell">
      <header className="commandBar">
        <div className="brandLockup">
          <span>RPA</span>
          <strong>Harness</strong>
        </div>
        <nav className="modeSwitch" aria-label="Dashboard sections">
          {tabs.map(([id, label]) => (
            <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </nav>
        <label className="runPicker">
          <span>Run</span>
          <select value={selectedRun} onChange={(event) => setSelectedRun(event.target.value)}>
            {runs.map((run) => <option key={run.run_id}>{run.run_id}</option>)}
          </select>
        </label>
        <button className="refresh" onClick={refresh}>Refresh</button>
      </header>

      <section className="consoleWorkspace">
        <div className="workspaceHeader">
          <span className="eyebrow">Read-only live evidence system</span>
          <h2>{title}</h2>
        </div>
        {error && <div className="error">{error}</div>}
        {tab === "monitor" && (
          <Monitor
            run={selected}
            detail={runDetail}
            timeline={timeline}
            records={records}
            steps={runSteps}
            failures={runFailures}
            repairs={selectedRepairs}
            desktopEvidence={desktopEvidence}
            graph={graph}
            summary={summary}
          />
        )}
        {tab === "history" && <History runs={runs} select={(runId) => { setSelectedRun(runId); setTab("monitor"); }} />}
        {tab === "builder" && <BuilderView rows={builders} />}
      </section>
    </main>
  );
}

function Monitor({
  run,
  detail,
  timeline,
  records,
  steps,
  failures,
  repairs,
  desktopEvidence,
  graph,
  summary,
}: {
  run?: Run;
  detail: RunDetail;
  timeline: TimelineEvent[];
  records: RecordResult[];
  steps: RunStep[];
  failures: Failure[];
  repairs: Failure[];
  desktopEvidence: DesktopEvidence[];
  graph: WorkflowGraph | null;
  summary: Record<string, unknown>;
}) {
  if (!run && !detail.manifest) return <Empty text="No run selected" />;
  const currentRun = run || detail.manifest;
  const latest = timeline[timeline.length - 1];
  const process = buildProcess(timeline, steps, graph);
  const narrative = buildNarrative(timeline);
  const recordCounts = countRecords(currentRun, records);
  const stepCounts = countSteps(currentRun, process);
  const incident = failures[0] || repairs[0];
  const evidence = buildEvidenceEntries(currentRun?.run_id || "", detail, incident, failures, repairs, desktopEvidence);
  const status = currentRun?.status || latest?.status || "waiting";
  const currentStep = latest?.step_id || latest?.record_id || latest?.phase || latest?.event || "Waiting for events";

  return (
    <div className="monitorBoard">
      <section className={`flightDeck ${status}`}>
        <div>
          <span className="eyebrow">Selected run</span>
          <h3>{currentRun?.workflow || "-"}</h3>
          <p>{currentRun?.run_id || "-"}</p>
        </div>
        <div className="deckMetrics">
          <div className="statusBadge">{status}</div>
          <Metric label="Current" value={currentStep} tone={latest?.status} />
          <Metric label="Steps" value={`${stepCounts.passed}/${stepCounts.total}`} tone={stepCounts.failed ? "failed" : status} />
          <Metric label="Records" value={`${recordCounts.passed}/${recordCounts.total}`} tone={recordCounts.failed ? "failed" : status} />
          <Metric label="Failures" value={String(failures.length)} tone={failures.length ? "failed" : "passed"} />
        </div>
      </section>

      <ProcessRail phases={process} />

      <div className="operationsGrid">
        <LiveNarrative rows={narrative} recordCounts={recordCounts} />
        <OperatorPanel
          run={currentRun}
          latest={latest}
          incident={incident}
          repair={repairs[0]}
          evidenceCount={evidence.length}
        />
      </div>

      <EvidenceTray runId={currentRun?.run_id || ""} rows={evidence} />

      <DeveloperDetails
        value={{
          manifest: detail.manifest || run || {},
          timeline,
          records,
          steps,
          failures,
          repairs,
          desktopEvidence,
          summary,
        }}
      />
    </div>
  );
}

function ProcessRail({ phases }: { phases: ProcessPhase[] }) {
  if (!phases.length) return <section className="stepMapDeck"><PanelTitle title="Process map" meta="no steps yet" /><Empty text="Waiting for step evidence" /></section>;
  return (
    <section className="stepMapDeck">
      <PanelTitle title="Process map" meta={`${phases.reduce((count, phase) => count + phase.steps.length, 0)} steps`} />
      <div className="stepMap">
        {phases.map((phase) => (
          <div key={phase.id} className="phaseLane">
            <h3>{phase.name}</h3>
            {phase.steps.map((step) => (
              <div key={`${phase.id}-${step.id}`} className={`processStep ${step.status}`}>
                <div className="stepMarker" aria-hidden="true" />
                <div className="stepMain">
                  <strong>{humanStep(step.id)}</strong>
                  <span>{step.actionType}</span>
                  {step.message && <p>{step.message}</p>}
                </div>
                <div className="stepBadges">
                  <Badge value={`${step.proofCount || 1} proof`} />
                  {step.durationMs !== undefined && <Badge value={formatDuration(step.durationMs)} />}
                  <Badge value={step.sideEffect} />
                  <Badge value={step.selectorQuality} />
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

function LiveNarrative({ rows, recordCounts }: { rows: NarrativeItem[]; recordCounts: ReturnType<typeof countRecords> }) {
  return (
    <section className="liveConsole">
      <PanelTitle title="Live log" meta={`${rows.length} visible events`} />
      <div className="recordMeter">
        <div>
          <strong>{recordCounts.passed}</strong>
          <span>records proven</span>
        </div>
        <div className="meterTrack">
          <span style={{ width: `${percent(recordCounts.passed, recordCounts.total)}%` }} />
        </div>
        <small>{recordCounts.failed ? `${recordCounts.failed} failed` : "No failed records"}</small>
      </div>
      <ol className="eventFeed">
        {rows.length ? rows.map((event) => (
          <li key={event.id} className={`${event.status} ${event.kind}`}>
            <span>{event.meta}</span>
            <strong>{event.title}</strong>
            <p>{event.body}</p>
          </li>
        )) : <li><strong>No events</strong><p>Waiting for timeline data.</p></li>}
      </ol>
    </section>
  );
}

function OperatorPanel({
  run,
  latest,
  incident,
  repair,
  evidenceCount,
}: {
  run?: Run;
  latest?: TimelineEvent;
  incident?: Failure;
  repair?: Failure;
  evidenceCount: number;
}) {
  const blocked = Boolean(incident?.failure_kind || incident?.message || run?.status === "failed");
  const title = blocked ? "Needs attention" : run?.status === "passed" ? "Run complete" : "Watching live";
  const nextAction = blocked
    ? safeText(repair?.recommended_next_action || "Inspect the evidence and repair packet before rerun.")
    : run?.status === "passed"
      ? "Review the report and keep the run as evidence."
      : "Monitor the current proof checks.";
  return (
    <section className={`decisionPanel ${blocked ? "failed" : run?.status || ""}`}>
      <PanelTitle title="Decision" meta={title} />
      <div className="operatorCallout">
        <strong>{blocked ? safeText(incident?.failure_kind || "Failure") : safeText(latest?.event || run?.status || "Waiting")}</strong>
        <p>{safeText(incident?.message || latest?.message || nextAction)}</p>
      </div>
      <KeyValue rows={[
        { label: "Next", value: nextAction },
        { label: "Safe retry", value: safeText(incident?.safe_retry ?? repair?.safe_retry ?? "not stated") },
        { label: "Failed step", value: safeText(incident?.step_id || latest?.step_id || "-") },
        { label: "Evidence", value: `${evidenceCount} linked artifacts` },
      ]} />
    </section>
  );
}

function EvidenceTray({ runId, rows }: { runId: string; rows: EvidenceEntry[] }) {
  return (
    <section className="evidenceWall">
      <PanelTitle title="Evidence wall" meta={`${rows.length} artifacts`} />
      {rows.length ? (
        <div className="artifactGrid">
          {rows.map((row) => <ArtifactLink key={`${row.kind}-${row.path}`} runId={runId} row={row} />)}
        </div>
      ) : <Empty text="No evidence artifacts for this run" />}
    </section>
  );
}

function ArtifactLink({ runId, row }: { runId: string; row: EvidenceEntry }) {
  const href = artifactUrl(runId, row.path);
  return href ? (
    <a className="artifact" href={href} target="_blank" rel="noreferrer">
      <ArtifactPreview href={href} kind={row.kind} />
      <strong>{row.label}</strong>
      <span>{row.kind}</span>
    </a>
  ) : (
    <div className="artifact">
      <strong>{row.label}</strong>
      <span>{row.kind}</span>
    </div>
  );
}

function ArtifactPreview({ href, kind }: { href: string; kind: string }) {
  if (kind === "image" || kind === "gif") {
    return (
      <span className={`artifactPreview ${kind}`}>
        <img src={href} alt="" loading="lazy" />
      </span>
    );
  }
  if (kind === "video" || kind === "log") return <span className={`artifactPreview ${kind}`}>{kind}</span>;
  return null;
}

function History({ runs, select }: { runs: Run[]; select: (runId: string) => void }) {
  if (!runs.length) return <Empty text="No runs indexed" />;
  return (
    <div className="runBoard">
      {runs.map((run) => (
        <button key={run.run_id} className={`historyItem ${run.status || ""}`} onClick={() => select(run.run_id)}>
          <strong>{run.workflow || "-"}</strong>
          <span>{run.status || "-"}</span>
          <small>{run.run_id}</small>
          <small>{run.started_at || run.finished_at || "-"}</small>
        </button>
      ))}
    </div>
  );
}

function BuilderView({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (!rows.length) return <Empty text="No builder sessions" />;
  return (
    <div className="builderView">
      <div className="runBoard">
        {rows.map((session, index) => (
          <div key={String(session.session_id || index)} className={`historyItem ${safeText(session.status)}`}>
            <strong>{safeText(session.session_id || "session")}</strong>
            <span>{safeText(session.status || "-")}</span>
            <small>{safeText(session.path || session.created_at || "-")}</small>
          </div>
        ))}
      </div>
      <DeveloperDetails value={rows} />
    </div>
  );
}

function DeveloperDetails({ value }: { value: unknown }) {
  return (
    <details className="developerDetails">
      <summary>Developer details</summary>
      <JsonBlock value={value} />
    </details>
  );
}

function buildProcess(timeline: TimelineEvent[], steps: RunStep[], graph: WorkflowGraph | null): ProcessPhase[] {
  const byStep = new Map<string, ProcessStep>();
  if (graph) {
    for (const phase of graph.phases) {
      for (const step of phase.steps) {
        byStep.set(step.id, {
          id: step.id,
          phase: phase.name || phase.id,
          status: "waiting",
          actionType: step.action_type || "action",
          proofCount: step.success_checks.length,
          sideEffect: step.side_effect || "none",
          selectorQuality: step.selector_quality || "unknown",
        });
      }
    }
  }

  for (const step of steps) {
    const id = step.step_id || step.record_id || "step";
    byStep.set(id, {
      ...byStep.get(id),
      id,
      phase: step.phase_id || byStep.get(id)?.phase || "Workflow",
      status: normalizeStatus(step.status),
      actionType: step.action_type || byStep.get(id)?.actionType || "action",
      proofCount: byStep.get(id)?.proofCount || 1,
      sideEffect: step.side_effect || byStep.get(id)?.sideEffect || "unknown",
      selectorQuality: step.selector_quality || byStep.get(id)?.selectorQuality || "unknown",
      durationMs: step.duration_ms,
      failureKind: step.failure_kind,
      message: step.message,
    });
  }

  for (const event of timeline) {
    if (!event.step_id || !String(event.event || "").startsWith("step.")) continue;
    const current = byStep.get(event.step_id);
    byStep.set(event.step_id, {
      ...current,
      id: event.step_id,
      phase: event.phase || event.phase_id || current?.phase || "Workflow",
      status: normalizeStatus(event.status || event.event),
      actionType: event.action_type || current?.actionType || "action",
      proofCount: current?.proofCount || (event.event === "step.passed" ? 1 : 0),
      sideEffect: current?.sideEffect || "unknown",
      selectorQuality: current?.selectorQuality || "unknown",
      durationMs: event.duration_ms,
      failureKind: event.failure_kind,
      message: event.message,
    });
  }

  const phases = new Map<string, ProcessPhase>();
  for (const step of byStep.values()) {
    const phase = phases.get(step.phase) || { id: step.phase, name: step.phase, steps: [] };
    phase.steps.push(step);
    phases.set(step.phase, phase);
  }
  return Array.from(phases.values());
}

function buildNarrative(timeline: TimelineEvent[]): NarrativeItem[] {
  let recordsPassed = 0;
  let rowEvents = 0;
  const items: NarrativeItem[] = [];
  for (const event of timeline) {
    const name = String(event.event || "");
    if (name === "record.passed") {
      recordsPassed += 1;
      continue;
    }
    if (name.includes(".row.")) {
      rowEvents += 1;
      continue;
    }
    items.push({
      id: timelineKey(event),
      title: humanEvent(name),
      body: safeText(event.message || event.step_id || event.record_id || event.phase || "-"),
      meta: event.event_id ? `#${event.event_id}` : shortTime(event.timestamp),
      status: normalizeStatus(event.status),
      kind: eventKind(name, event.status),
    });
  }
  if (recordsPassed || rowEvents) {
    items.push({
      id: "record-summary",
      title: "Record progress grouped",
      body: `${recordsPassed} records passed${rowEvents ? `, ${rowEvents} row events compressed` : ""}.`,
      meta: "records",
      status: "passed",
      kind: "record",
    });
  }
  return items.slice(-14);
}

function buildEvidenceEntries(
  runId: string,
  detail: RunDetail,
  incident: Failure | undefined,
  failures: Failure[],
  repairs: Failure[],
  desktopEvidence: DesktopEvidence[],
): EvidenceEntry[] {
  const rows: EvidenceEntry[] = [];
  addEvidence(rows, "Report", detail.report_html, "html");
  addEvidence(rows, "Failure report", incident?.evidence_bundle_path || failures[0]?.evidence_bundle_path, "failure");
  addEvidence(rows, "Repair packet", incident?.repair_packet_path || repairs[0]?.repair_packet_path, "repair");
  for (const item of desktopEvidence.slice(0, 6)) {
    addEvidence(rows, "Screenshot", item.screenshot_path, "image");
    addEvidence(rows, "Animated capture", item.gif_path || item.recording_path, "gif");
    addEvidence(rows, "Screen recording", item.video_path, "video");
    addEvidence(rows, "UIA tree", item.uia_snapshot_path || item.win32_snapshot_path, "desktop");
    addEvidence(rows, "OCR", item.ocr_artifact_path, "desktop");
    addEvidence(rows, "API preview", item.api_preview_path, "api");
    addEvidence(rows, "Logs", item.logs_path, "log");
  }
  const seen = new Set<string>();
  return rows.filter((row) => {
    const key = `${row.kind}:${relativeArtifactPath(runId, row.path)}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function addEvidence(rows: EvidenceEntry[], label: string, path: unknown, kind: string) {
  const text = safeText(path);
  if (text && text !== "-") rows.push({ label, path: text, kind });
}

function countRecords(run: Run | undefined, records: RecordResult[]) {
  const passed = numberFromSummary(run, "passed_records", records.filter((record) => record.status === "passed").length);
  const failed = numberFromSummary(run, "failed_records", records.filter((record) => record.status === "failed").length);
  const skipped = numberFromSummary(run, "skipped_records", records.filter((record) => record.status === "skipped").length);
  const total = numberFromSummary(run, "total_records", records.length || passed + failed + skipped);
  return { total, passed, failed, skipped };
}

function countSteps(run: Run | undefined, phases: ProcessPhase[]) {
  const steps = phases.flatMap((phase) => phase.steps);
  const passed = numberFromSummary(run, "passed_steps", steps.filter((step) => step.status === "passed").length);
  const failed = numberFromSummary(run, "failed_steps", steps.filter((step) => step.status === "failed").length);
  const total = numberFromSummary(run, "total_steps", steps.length || passed + failed);
  return { total, passed, failed };
}

function numberFromSummary(run: Run | undefined, key: string, fallback: number): number {
  return Number(run?.summary?.[key] ?? fallback ?? 0);
}

function percent(value: number, total: number): number {
  if (!total) return 0;
  return Math.max(0, Math.min(100, Math.round((value / total) * 100)));
}

function normalizeStatus(value: unknown): string {
  const text = safeText(value).toLowerCase();
  if (text.includes("fail") || text.includes("error")) return "failed";
  if (text.includes("pass") || text.includes("finish")) return "passed";
  if (text.includes("skip")) return "skipped";
  if (text.includes("start") || text.includes("run")) return "running";
  return text && text !== "-" ? text : "waiting";
}

function humanEvent(value: string): string {
  if (!value) return "Event";
  return value.replace(/\./g, " ").replace(/\b\w/g, (letter: string) => letter.toUpperCase());
}

function humanStep(value: string): string {
  return value.replace(/^Step\s+\d+:\s*/i, "").replace(/_/g, " ");
}

function eventKind(event: string, status: unknown): string {
  const state = normalizeStatus(status || event);
  if (state === "failed") return "failure";
  if (event.includes("record")) return "record";
  if (event.includes("evidence") || event.includes("screenshot")) return "evidence";
  if (event.includes("step")) return "step";
  return "system";
}

function formatDuration(value: number): string {
  if (value < 1000) return `${Math.round(value)}ms`;
  return `${Math.round(value / 100) / 10}s`;
}

function shortTime(value: unknown): string {
  const text = safeText(value);
  return text === "-" ? "-" : text.slice(11, 19) || text;
}

function safeText(value: unknown): string {
  if (value === undefined || value === null || value === "") return "-";
  return String(value);
}

function relativeArtifactPath(runId: string, path: string): string {
  const normalized = path.replace(/\\/g, "/");
  const runMarker = `/runs/${runId}/`;
  const runIndex = normalized.indexOf(runMarker);
  if (runIndex >= 0) return normalized.slice(runIndex + runMarker.length);
  const idMarker = `${runId}/`;
  const idIndex = normalized.lastIndexOf(idMarker);
  if (idIndex >= 0) return normalized.slice(idIndex + idMarker.length);
  return normalized;
}

function artifactUrl(runId: string, path: string): string {
  const relative = relativeArtifactPath(runId, path);
  return runId && relative ? `/api/artifacts?run_id=${encodeURIComponent(runId)}&path=${encodeURIComponent(relative)}` : "";
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return <div className={`metric ${tone || ""}`}><span>{label}</span><strong>{value}</strong></div>;
}

function Badge({ value }: { value: string }) {
  return <em>{value}</em>;
}

function PanelTitle({ title, meta }: { title: string; meta?: string }) {
  return (
    <div className="panelTitle">
      <h3>{title}</h3>
      {meta && <span>{meta}</span>}
    </div>
  );
}

function KeyValue({ rows }: { rows: Array<{ label: string; value: string }> }) {
  return (
    <dl className="facts">
      {rows.map((row) => (
        <div key={row.label}>
          <dt>{row.label}</dt>
          <dd>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="empty">{text}</div>;
}

function JsonBlock({ value }: { value: unknown }) {
  return <pre className="json">{JSON.stringify(value, null, 2)}</pre>;
}
