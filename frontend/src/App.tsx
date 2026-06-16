import { useEffect, useMemo, useState } from "react";
import { api, CopilotSession, Failure, RecordResult, Run, TimelineEvent, WorkflowGraph } from "./api/client";

type RunDetailPayload = {
  manifest?: Record<string, unknown>;
  report_html?: string;
};

type Tab =
  | "runs"
  | "copilot"
  | "run"
  | "live"
  | "workflow"
  | "records"
  | "failures"
  | "evidence"
  | "selectors"
  | "repairs"
  | "summary"
  | "builders";

const tabs: Array<[Tab, string]> = [
  ["copilot", "Copilot"],
  ["runs", "Runs"],
  ["run", "Run Detail"],
  ["live", "Live"],
  ["workflow", "Workflow"],
  ["records", "Records"],
  ["failures", "Failures"],
  ["evidence", "Evidence"],
  ["selectors", "Selectors"],
  ["repairs", "Repair Packets"],
  ["summary", "Summary"],
  ["builders", "Builders"],
];

export function App() {
  const [tab, setTab] = useState<Tab>("copilot");
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRun, setSelectedRun] = useState("");
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [records, setRecords] = useState<RecordResult[]>([]);
  const [failures, setFailures] = useState<Failure[]>([]);
  const [selectors, setSelectors] = useState<Failure[]>([]);
  const [repairs, setRepairs] = useState<Failure[]>([]);
  const [summary, setSummary] = useState<Record<string, unknown>>({});
  const [builders, setBuilders] = useState<Array<Record<string, unknown>>>([]);
  const [copilotSessions, setCopilotSessions] = useState<CopilotSession[]>([]);
  const [selectedCopilot, setSelectedCopilot] = useState("");
  const [copilotDetail, setCopilotDetail] = useState<CopilotSession | null>(null);
  const [runDetail, setRunDetail] = useState<RunDetailPayload | null>(null);
  const [workflowPath, setWorkflowPath] = useState("workflows/examples/minimal_example.yaml");
  const [graph, setGraph] = useState<WorkflowGraph | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (!selectedRun) return;
    let active = true;
    Promise.all([api.getTimeline(selectedRun), api.getRun(selectedRun)])
      .then(([timelineData, detailData]) => {
        if (!active) return;
        setTimeline(timelineData.events);
        setRunDetail(detailData as RunDetailPayload);
      })
      .catch(showError);
    return () => {
      active = false;
    };
  }, [selectedRun]);

  useEffect(() => {
    if (!selectedCopilot) return;
    let active = true;
    api.getCopilotSession(selectedCopilot)
      .then((session) => {
        if (active) setCopilotDetail(session);
      })
      .catch(showError);
    return () => {
      active = false;
    };
  }, [selectedCopilot]);

  useEffect(() => {
    if (tab !== "live" || !selectedRun) return;
    const timer = window.setInterval(async () => {
      const last = timeline.reduce((max, event) => Math.max(max, Number(event.event_id || 0)), 0);
      const data = await api.pollEvents(selectedRun, last);
      if (data.events.length) {
        setTimeline((current) => [...current, ...data.events].slice(-100));
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [tab, selectedRun, timeline]);

  const selected = useMemo(
    () => runs.find((run) => run.run_id === selectedRun) || runs[0],
    [runs, selectedRun],
  );

  async function refresh() {
    setError("");
    try {
      const [runData, recordData, failureData, selectorData, repairData, summaryData, builderData, copilotData] =
        await Promise.all([
          api.listRuns(),
          api.getRecords(),
          api.getFailures(),
          api.getSelectors(),
          api.getRepairPackets(),
          api.getSummary(),
          api.getBuilders(),
          api.getCopilotSessions(),
        ]);
      setRuns(runData.runs);
      setSelectedRun((current) => current || runData.runs[0]?.run_id || "");
      setCopilotSessions(copilotData.sessions);
      setSelectedCopilot((current) => current || copilotData.sessions[0]?.session_id || "");
      setRecords(recordData.records);
      setFailures(failureData.failures);
      setSelectors(selectorData.selector_failures);
      setRepairs(repairData.repair_packets);
      setSummary(summaryData);
      setBuilders(builderData.sessions);
    } catch (err) {
      showError(err);
    }
  }

  async function loadGraph() {
    setError("");
    try {
      setGraph(await api.getWorkflowGraph(workflowPath));
    } catch (err) {
      showError(err);
    }
  }

  function showError(err: unknown) {
    setError(err instanceof Error ? err.message : String(err));
  }

  return (
    <main className="shell">
      <aside className="rail">
        <div className="brand">
          <h1>RPA Harness</h1>
          <span>{runs.length ? `${runs.length} runs indexed` : "Evidence console"}</span>
        </div>
        <nav>
          {tabs.map(([id, label]) => (
            <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)} aria-current={tab === id ? "page" : undefined}>
              {label}
            </button>
          ))}
        </nav>
        <button className="refresh" onClick={refresh}>Refresh</button>
      </aside>
      <section className="workspace">
        <header className="topbar">
          <div>
            <span className="eyebrow">Run ledger</span>
            <h2>{tabs.find(([id]) => id === tab)?.[1]}</h2>
          </div>
          {tab === "copilot" ? (
            <label>
              Session
              <select value={selectedCopilot} onChange={(event) => setSelectedCopilot(event.target.value)}>
                {copilotSessions.map((session) => <option key={session.session_id}>{session.session_id}</option>)}
              </select>
            </label>
          ) : (
            <label>
              Run
              <select value={selectedRun} onChange={(event) => setSelectedRun(event.target.value)}>
                {runs.map((run) => <option key={run.run_id}>{run.run_id}</option>)}
              </select>
            </label>
          )}
        </header>
        {error && <div className="error">{error}</div>}
        {tab === "copilot" && <Copilot sessions={copilotSessions} detail={copilotDetail} select={setSelectedCopilot} />}
        {tab === "runs" && <Runs runs={runs} select={(runId) => { setSelectedRun(runId); setTab("run"); }} />}
        {tab === "run" && <RunDetail run={selected} detail={runDetail} timeline={timeline} records={records.filter((record) => record.run_id === selected?.run_id)} />}
        {tab === "live" && <Live run={selected} timeline={timeline} />}
        {tab === "workflow" && <Workflow path={workflowPath} setPath={setWorkflowPath} graph={graph} load={loadGraph} />}
        {tab === "records" && <Records rows={records} />}
        {tab === "failures" && <Failures rows={failures} />}
        {tab === "evidence" && <Evidence rows={failures} />}
        {tab === "selectors" && <Failures rows={selectors} />}
        {tab === "repairs" && <Failures rows={repairs} />}
        {tab === "summary" && <JsonBlock value={summary} />}
        {tab === "builders" && <JsonBlock value={builders} />}
      </section>
    </main>
  );
}

function Copilot({ sessions, detail, select }: { sessions: CopilotSession[]; detail: CopilotSession | null; select: (sessionId: string) => void }) {
  const session = detail || sessions[0];
  if (!session) return <Empty text="No copilot sessions" />;
  const next = asRecord(session.next_question);
  const run = asRecord(session.run);
  const artifacts = asRecord(session.artifacts);
  const report = String(artifacts.report || run.report || "");
  return (
    <div className="stack">
      <section className="runHero copilotHero">
        <div>
          <span className="eyebrow">Automation copilot</span>
          <h3>{session.session_id}</h3>
          <p>{session.workflow_path || session.target_url || "Session is waiting for workflow or discovery evidence."}</p>
        </div>
        {report && <a className="reportLink" href={reportHref(report)} target="_blank" rel="noreferrer">Open report</a>}
      </section>
      <div className="metrics">
        <Metric label="Status" value={session.status || "-"} tone={session.status} />
        <Metric label="Phase" value={session.phase || "-"} />
        <Metric label="Question" value={String(next.id || "none")} />
        <Metric label="Updated" value={shortDate(session.updated_at || "") || "-"} />
      </div>
      {next.id ? <QuestionPanel question={next} /> : <Empty text="No active question" />}
      <div className="splitGrid">
        <section className="miniBlock">
          <h3>Sessions</h3>
          <Table rows={sessions as unknown as Array<Record<string, unknown>>} columns={["session_id", "phase", "status", "updated_at"]} onFirst={select} />
        </section>
        <section className="miniBlock">
          <h3>Answers</h3>
          <Table rows={(session.answers || []) as Array<Record<string, unknown>>} columns={["question_id", "answer", "answered_at"]} />
        </section>
      </div>
      <JsonBlock value={{
        discovery: session.discovery,
        validation: session.validation,
        preflight: session.preflight,
        run: session.run,
        artifacts: session.artifacts,
      }} />
    </div>
  );
}

function QuestionPanel({ question }: { question: Record<string, unknown> }) {
  const choices = Array.isArray(question.choices) ? question.choices.map(String) : [];
  return (
    <section className="questionPanel">
      <div>
        <span className="eyebrow">Next question</span>
        <h3>{String(question.id || "-")}</h3>
        <p>{String(question.question || "")}</p>
      </div>
      <div className="choiceRow">
        {choices.map((choice) => <span key={choice} className="pill">{choice}</span>)}
      </div>
      <JsonBlock value={question.details || {}} />
    </section>
  );
}

function Runs({ runs, select }: { runs: Run[]; select: (runId: string) => void }) {
  return <Table rows={runs} columns={["run_id", "workflow", "status", "started_at"]} onFirst={select} />;
}

function RunDetail({ run, detail, timeline, records }: { run?: Run; detail: RunDetailPayload | null; timeline: TimelineEvent[]; records: RecordResult[] }) {
  if (!run) return <Empty text="No run selected" />;
  const manifest = asRecord(detail?.manifest);
  const summary = asRecord(manifest.summary || run.summary);
  const reportPath = String(detail?.report_html || run.report_path || run.report || "");
  const steps = pair(summary, "passed_steps", "total_steps", timeline.filter((event) => event.event === "step.passed").length);
  const recordCount = pair(summary, "passed_records", "total_records", records.filter((record) => record.status === "passed").length);
  return (
    <div className="stack">
      <section className="runHero">
        <div>
          <span className="eyebrow">Selected run</span>
          <h3>{run.run_id}</h3>
          <p>{run.workflow || String(manifest.workflow || "-")} finished with {timeline.length} timeline events.</p>
        </div>
        {reportPath && <a className="reportLink" href={reportHref(reportPath)} target="_blank" rel="noreferrer">Open report</a>}
      </section>
      <div className="metrics">
        <Metric label="Workflow" value={run.workflow || "-"} />
        <Metric label="Status" value={run.status || "-"} tone={run.status} />
        <Metric label="Steps" value={steps} />
        <Metric label="Records" value={recordCount} />
      </div>
      <Timeline rows={timeline} />
      <Records rows={records} />
    </div>
  );
}

function Live({ run, timeline }: { run?: Run; timeline: TimelineEvent[] }) {
  const latest = timeline[timeline.length - 1];
  return (
    <div className="stack">
      <div className="metrics">
        <Metric label="Run" value={run?.run_id || "-"} />
        <Metric label="Current event" value={latest?.event || "-"} tone={latest?.status} />
        <Metric label="Phase" value={latest?.phase || latest?.phase_id || "-"} />
        <Metric label="Step" value={latest?.step_id || "-"} />
      </div>
      <Timeline rows={timeline.slice(-100)} />
    </div>
  );
}

function Workflow({ path, setPath, graph, load }: { path: string; setPath: (value: string) => void; graph: WorkflowGraph | null; load: () => void }) {
  return (
    <div className="stack">
      <div className="toolbar">
        <input value={path} onChange={(event) => setPath(event.target.value)} />
        <button onClick={load}>Load Graph</button>
      </div>
      {!graph ? <Empty text="Load a workflow graph" /> : (
        <div className="phases">
          {graph.phases.map((phase) => (
            <section key={phase.id} className="phase">
              <h3>{phase.name || phase.id}</h3>
              {phase.steps.map((step) => (
                <div key={step.id} className="step">
                  <strong>{step.id}</strong>
                  <span>{step.action_type}</span>
                  <Badge value={`${step.success_checks.length} checks`} />
                  <Badge value={step.side_effect || "none"} />
                  <Badge value={step.selector_quality || "unknown"} />
                </div>
              ))}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

function Records({ rows }: { rows: RecordResult[] }) {
  return <Table rows={rows} columns={["record_id", "workflow", "run_id", "status", "failed_step", "failure_kind", "safe_retry", "evidence_bundle_path"]} />;
}

function Failures({ rows }: { rows: Failure[] }) {
  return <Table rows={rows} columns={["failure_kind", "workflow", "run_id", "phase_id", "step_id", "record_id", "evidence_bundle_path", "repair_packet_path", "message"]} />;
}

function Evidence({ rows }: { rows: Failure[] }) {
  return <Table rows={rows} columns={["workflow", "run_id", "step_id", "record_id", "failure_kind", "evidence_bundle_path", "repair_packet_path"]} />;
}

function Timeline({ rows }: { rows: TimelineEvent[] }) {
  return <Table rows={rows} columns={["event_id", "timestamp", "event", "status", "phase_id", "phase", "step_id", "record_id", "failure_kind", "message"]} />;
}

function Table<T extends Record<string, unknown>>({ rows, columns, onFirst }: { rows: T[]; columns: string[]; onFirst?: (value: string) => void }) {
  if (!rows.length) return <Empty text="No rows" />;
  return (
    <div className="tableWrap">
      <table>
        <thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {columns.map((column, columnIndex) => (
                <td key={column} className={columnIndex === 0 && onFirst ? "selectableCell" : ""} onClick={columnIndex === 0 && onFirst ? () => onFirst(String(row[column] || "")) : undefined}>
                  <Cell column={column} value={row[column]} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Cell({ column, value }: { column: string; value: unknown }) {
  const text = String(value ?? "");
  if (column === "status" || column === "failure_kind" || column === "safe_retry") {
    return <span className={`pill ${text || "emptyValue"}`}>{text || "-"}</span>;
  }
  if (column === "timestamp" || column.endsWith("_at")) {
    return <time>{shortDate(text)}</time>;
  }
  return <>{text}</>;
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return <div className={`metric ${tone || ""}`}><span>{label}</span><strong>{value}</strong></div>;
}

function Badge({ value }: { value: string }) {
  return <em>{value}</em>;
}

function Empty({ text }: { text: string }) {
  return <div className="empty">{text}</div>;
}

function JsonBlock({ value }: { value: unknown }) {
  return <pre className="json">{JSON.stringify(value, null, 2)}</pre>;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function pair(summary: Record<string, unknown>, passedKey: string, totalKey: string, fallbackPassed: number): string {
  const passed = summary[passedKey] ?? fallbackPassed;
  const total = summary[totalKey] ?? (fallbackPassed || "-");
  return `${passed}/${total}`;
}

function reportHref(path: string): string {
  if (path.startsWith("http") || path.startsWith("/")) return path;
  return `file:///${path.replace(/\\/g, "/")}`;
}

function shortDate(value: string): string {
  if (!value) return "";
  return value.replace("T", " ").slice(0, 19);
}
