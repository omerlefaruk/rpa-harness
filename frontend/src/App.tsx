import { useEffect, useMemo, useState } from "react";
import { api, Failure, RecordResult, Run, TimelineEvent, WorkflowGraph } from "./api/client";

type Tab =
  | "runs"
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
  const [tab, setTab] = useState<Tab>("runs");
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRun, setSelectedRun] = useState("");
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [records, setRecords] = useState<RecordResult[]>([]);
  const [failures, setFailures] = useState<Failure[]>([]);
  const [selectors, setSelectors] = useState<Failure[]>([]);
  const [repairs, setRepairs] = useState<Failure[]>([]);
  const [summary, setSummary] = useState<Record<string, unknown>>({});
  const [builders, setBuilders] = useState<Array<Record<string, unknown>>>([]);
  const [workflowPath, setWorkflowPath] = useState("workflows/examples/minimal_example.yaml");
  const [graph, setGraph] = useState<WorkflowGraph | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (!selectedRun) return;
    api.getTimeline(selectedRun).then((data) => setTimeline(data.events)).catch(showError);
  }, [selectedRun]);

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
      const [runData, recordData, failureData, selectorData, repairData, summaryData, builderData] =
        await Promise.all([
          api.listRuns(),
          api.getRecords(),
          api.getFailures(),
          api.getSelectors(),
          api.getRepairPackets(),
          api.getSummary(),
          api.getBuilders(),
        ]);
      setRuns(runData.runs);
      setSelectedRun((current) => current || runData.runs[0]?.run_id || "");
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
        <h1>RPA Harness</h1>
        <nav>
          {tabs.map(([id, label]) => (
            <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </nav>
        <button className="refresh" onClick={refresh}>Refresh</button>
      </aside>
      <section className="workspace">
        <header className="topbar">
          <div>
            <span className="eyebrow">Read-only operator layer</span>
            <h2>{tabs.find(([id]) => id === tab)?.[1]}</h2>
          </div>
          <label>
            Run
            <select value={selectedRun} onChange={(event) => setSelectedRun(event.target.value)}>
              {runs.map((run) => <option key={run.run_id}>{run.run_id}</option>)}
            </select>
          </label>
        </header>
        {error && <div className="error">{error}</div>}
        {tab === "runs" && <Runs runs={runs} select={(runId) => { setSelectedRun(runId); setTab("run"); }} />}
        {tab === "run" && <RunDetail run={selected} timeline={timeline} records={records.filter((record) => record.run_id === selected?.run_id)} />}
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

function Runs({ runs, select }: { runs: Run[]; select: (runId: string) => void }) {
  return <Table rows={runs} columns={["run_id", "workflow", "status", "started_at", "finished_at", "report_path", "report"]} onFirst={select} />;
}

function RunDetail({ run, timeline, records }: { run?: Run; timeline: TimelineEvent[]; records: RecordResult[] }) {
  if (!run) return <Empty text="No run selected" />;
  return (
    <div className="stack">
      <div className="metrics">
        <Metric label="Workflow" value={run.workflow || "-"} />
        <Metric label="Status" value={run.status || "-"} tone={run.status} />
        <Metric label="Steps" value={String(run.summary?.passed_steps ?? "-") + "/" + String(run.summary?.total_steps ?? "-")} />
        <Metric label="Records" value={String(run.summary?.passed_records ?? "-") + "/" + String(run.summary?.total_records ?? "-")} />
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
                <td key={column} onClick={columnIndex === 0 && onFirst ? () => onFirst(String(row[column] || "")) : undefined}>
                  {String(row[column] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
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
