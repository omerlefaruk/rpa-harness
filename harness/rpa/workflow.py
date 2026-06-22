"""
RPA Workflow base class for data-driven process automation.
Adapted from automation-harness with added batch processing,
record-level retry, and on_success callback.
"""

import html
import json
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from harness.config import HarnessConfig
from harness.core import ExecutionTrace
from harness.core.artifacts import read_json, write_json
from harness.core.time import utc_now_iso
from harness.logger import HarnessLogger
from harness.notifications import BotNotifier
from harness.rpa.ledger import ResumeLedger
from harness.resilience.errors import RPAError
from harness.security import redact_value, redacted_preview


class StepStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"
    RETRYING = "retrying"


@dataclass
class WorkflowStep:
    name: str
    status: StepStatus = StepStatus.PASSED
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_ms: float = 0.0
    input_data: dict = field(default_factory=dict)
    output_data: dict = field(default_factory=dict)
    error_message: Optional[str] = None
    screenshot: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "input": self.input_data,
            "output": self.output_data,
            "error": self.error_message,
            "screenshot": self.screenshot,
        }


class WorkflowStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class RetryableRecordError(RPAError):
    code = "RETRYABLE_RECORD"
    category = "TRANSIENT"

    def __init__(self, result: dict):
        message = result.get("reason") or result.get("status") or "Retryable workflow result"
        super().__init__(message, details={"result": result})
        self.result = result


@dataclass
class WorkflowResult:
    name: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_ms: float = 0.0
    total_records: int = 0
    processed_records: int = 0
    failed_records: int = 0
    skipped_records: int = 0
    retried_records: int = 0
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None
    steps: list = field(default_factory=list)
    screenshots: list = field(default_factory=list)
    output_files: list = field(default_factory=list)
    logs: list = field(default_factory=list)
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "total_records": self.total_records,
            "processed_records": self.processed_records,
            "failed_records": self.failed_records,
            "skipped_records": self.skipped_records,
            "retried_records": self.retried_records,
            "error_message": self.error_message,
            "steps": [s.to_dict() for s in self.steps],
            "screenshots": self.screenshots,
            "output_files": self.output_files,
            "logs": self.logs,
            "data": self.data,
        }

    @property
    def passed(self) -> bool:
        return self.status == WorkflowStatus.PASSED


class RPAWorkflow:
    name: str = "unnamed-workflow"
    tags: List[str] = []
    max_retries_per_record: int = 2
    retry_base_delay_ms: int = 1000
    allow_mismatches: bool = False

    def __init__(self, config: Optional[HarnessConfig] = None):
        self.config = config
        self.result = WorkflowResult(name=self.name)
        self.logger = HarnessLogger(f"workflow.{self.name}")
        self.notifier = BotNotifier.from_env(source=f"workflow.{self.name}")
        self._step_index = 0
        self._current_record: Optional[dict] = None
        self._batch_size: int = 1
        self._trace = ExecutionTrace()
        self.current_stage: Optional[str] = None
        self._last_record_attempts: int = 0
        self._pending_record_evidence: list[dict] = []
        self._resume_ledger = self._build_resume_ledger()
        self._run_id: Optional[str] = None
        self._run_dir: Optional[Path] = None
        self._timeline_event_id = 0

    async def setup(self):
        pass

    def get_records(self) -> Iterator[dict]:
        raise NotImplementedError("Subclasses must implement get_records()")

    async def process_record(self, record: dict) -> dict:
        raise NotImplementedError("Subclasses must implement process_record()")

    async def on_mismatch(self, record: dict, reason: str, details: dict = None):
        self.log(f"MISMATCH: {reason} | Record: {redacted_preview(record)}")
        if details:
            self.log(f"Details: {redacted_preview(details)}")

    async def on_success(self, record: dict, details: dict = None):
        pass

    async def on_skip(self, record: dict, reason: str):
        self.log(f"SKIPPED: {reason} | Record: {redacted_preview(record)}")

    async def teardown(self):
        pass

    def log(self, message: str):
        self.result.logs.append(message)
        self.logger.info(message)

    def set_current_stage(self, stage: str) -> str:
        self.current_stage = stage
        self.result.data["current_stage"] = stage
        return stage

    def record_evidence(
        self,
        evidence: dict,
        record: Optional[dict] = None,
        stage: Optional[str] = None,
    ) -> dict:
        target_record = record or self._current_record or {}
        entry = {
            "record_id": self._record_id(target_record),
            "stage": stage or self.current_stage,
            "evidence": redact_value(evidence, max_chars=1000),
        }
        self.result.data.setdefault("record_evidence", []).append(entry)
        if target_record is self._current_record or record is None:
            self._pending_record_evidence.append(entry)
        return entry

    def step(self, name: str, input_data: dict = None) -> WorkflowStep:
        self._step_index += 1
        self.set_current_stage(name)
        step = WorkflowStep(
            name=f"Step {self._step_index}: {name}",
            start_time=datetime.now(),
            input_data=input_data or {},
        )
        self.result.steps.append(step)
        self._trace.start_step(name, index=self._step_index)
        self.result.data["execution_trace"] = self._trace.to_metadata()
        self.logger.info(f"  {step.name}")
        self._timeline("step.started", status="running", phase=name, step_id=step.name)
        return step

    def step_done(self, step: WorkflowStep, output_data: dict = None,
                  status: StepStatus = StepStatus.PASSED, error: str = None):
        step.end_time = datetime.now()
        step.output_data = output_data or {}
        step.status = status
        step.error_message = error
        if step.start_time:
            delta = step.end_time - step.start_time
            step.duration_ms = delta.total_seconds() * 1000
        self._trace.finish_current(status.value, error=error)
        self.result.data["execution_trace"] = self._trace.to_metadata()
        self._timeline(
            f"step.{status.value}",
            status=status.value,
            phase=step.name.split(": ", 1)[-1],
            step_id=step.name,
            duration_ms=step.duration_ms,
            message=error,
        )
        self._write_manifest(self.result.status.value)

    async def _execute(self) -> WorkflowResult:
        self.result.start_time = datetime.now()
        self.result.status = WorkflowStatus.RUNNING
        self._start_live_run()

        try:
            setup_step = self.step("Workflow Setup")
            await self.setup()
            self.step_done(setup_step)

            records = list(self.get_records())
            self.result.total_records = len(records)
            self._refresh_record_summary()
            self.log(f"Processing {len(records)} records...")

            processing_step = self.step("Process Records")
            for idx, record in enumerate(records, 1):
                self._current_record = record
                self._last_record_attempts = 0
                self._pending_record_evidence = []
                record_id = record.get("id") or record.get(
                    "reservation_number"
                ) or f"record_{idx}"

                try:
                    self.log(f"[{idx}/{len(records)}] Processing: {record_id}")
                    result = await self._process_with_retry(record)

                    status = result.get("status", "passed")
                    if status == "passed":
                        self.result.processed_records += 1
                        await self.on_success(record, result)
                    elif status == "skipped":
                        self.result.skipped_records += 1
                        await self.on_skip(record, result.get("reason", ""))
                    else:
                        self.result.failed_records += 1
                        await self.notifier.failure(
                            "A record did not pass validation.",
                            context={
                                "workflow": self.name,
                                "record_id": record_id,
                                "reason": result.get("reason", "Validation failed"),
                            },
                        )
                        await self.on_mismatch(
                            record,
                            result.get("reason", "Validation failed"),
                            result.get("details", {}),
                        )
                    self._record_terminal_outcome(record, record_id, result)
                except Exception as e:
                    self.result.failed_records += 1
                    self.log(f"  ERROR on {record_id}: {e}")
                    await self.notifier.failure(
                        "A record crashed while I was processing it.",
                        context={
                            "workflow": self.name,
                            "record_id": record_id,
                            "error": str(e),
                        },
                    )
                    await self.on_mismatch(
                        record, str(e), {"exception": traceback.format_exc()}
                    )
                    self._record_terminal_outcome(
                        record,
                        record_id,
                        {
                            "status": "failed",
                            "reason": str(e),
                            "details": {"exception": traceback.format_exc()},
                        },
                    )
                finally:
                    self._refresh_record_summary()
                    self._write_manifest(self.result.status.value)

            self.step_done(processing_step)

            if self.result.total_records == 0:
                self.result.status = WorkflowStatus.PASSED
            elif self.result.failed_records == 0:
                self.result.status = WorkflowStatus.PASSED
            elif self.allow_mismatches and self.result.processed_records > 0:
                self.result.status = WorkflowStatus.PASSED
            else:
                self.result.status = WorkflowStatus.FAILED
            self._write_manifest(self.result.status.value)

        except Exception as e:
            self.result.status = WorkflowStatus.FAILED
            self.result.error_message = str(e)
            self.result.stack_trace = traceback.format_exc()
            self.log(f"WORKFLOW ERROR: {e}")
            await self.notifier.failure(
                "The workflow crashed before it could finish.",
                context={"workflow": self.name, "error": str(e)},
            )
            self._timeline("run.failed", status="failed", failure_kind="workflow_error", message=str(e))

        finally:
            try:
                teardown_step = self.step("Workflow Teardown")
                await self.teardown()
                self.step_done(teardown_step)
            except Exception as e:
                self.log(f"TEARDOWN ERROR: {e}")
                await self.notifier.frustration(
                    "Cleanup failed after the workflow run.",
                    context={"workflow": self.name, "error": str(e)},
                )

            self.result.end_time = datetime.now()
            if self.result.start_time:
                delta = self.result.end_time - self.result.start_time
                self.result.duration_ms = delta.total_seconds() * 1000

            self.log(
                f"Complete: {self.result.processed_records} passed, "
                f"{self.result.failed_records} failed, "
                f"{self.result.skipped_records} skipped, "
                f"{self.result.retried_records} retried"
            )
            self._timeline("run.finished", status=self.result.status.value)
            self._write_manifest(self.result.status.value, finished=True)
            self._write_live_report()

        return self.result

    async def _process_with_retry(self, record: dict) -> dict:
        from harness.resilience.recovery import smart_retry

        attempts = 0

        async def operation() -> dict:
            nonlocal attempts
            attempts += 1

            result = await self.process_record(record)
            status = result.get("status", "passed")

            if status in ("passed", "skipped"):
                return result

            if self._is_retryable(status):
                raise RetryableRecordError(result)

            return result

        try:
            result = await smart_retry(
                operation,
                logger=self.logger,
                max_attempts_by_category={
                    "TRANSIENT": self.max_retries_per_record + 1,
                    "UNKNOWN": self.max_retries_per_record + 1,
                    "PERMANENT": 1,
                },
            )
            self.result.retried_records += max(0, attempts - 1)
            self._last_record_attempts = attempts
            if attempts > 1:
                await self.notifier.frustration(
                    "I had to retry a record before it passed.",
                    context={
                        "workflow": self.name,
                        "record_id": self._record_id(record),
                        "attempts": attempts,
                    },
                )
            return result
        except RetryableRecordError as e:
            self.result.retried_records += max(0, attempts - 1)
            self._last_record_attempts = attempts
            if attempts > 1:
                await self.notifier.frustration(
                    "I retried a record and it still did not pass.",
                    context={
                        "workflow": self.name,
                        "record_id": self._record_id(record),
                        "attempts": attempts,
                        "reason": str(e),
                    },
                )
            return e.result
        except Exception as e:
            self.result.retried_records += max(0, attempts - 1)
            self._last_record_attempts = attempts
            await self.notifier.frustration(
                "The record retry path ended in an exception.",
                context={
                    "workflow": self.name,
                    "record_id": self._record_id(record),
                    "attempts": attempts,
                    "error": str(e),
                },
            )
            return {"status": "failed", "reason": str(e)}

    @staticmethod
    def _is_retryable(status: str) -> bool:
        return status in ("failed", "error", "retry", "timeout")

    @staticmethod
    def _record_id(record: dict) -> str:
        return str(record.get("id") or record.get("reservation_number") or "unknown")

    @staticmethod
    def _terminal_record_status(status: str) -> str:
        if status in ("passed", "skipped", "needs_review"):
            return status
        return "failed"

    def _record_terminal_outcome(
        self,
        record: dict,
        record_id: str,
        result: dict,
    ) -> dict:
        raw_status = str(result.get("status", "passed"))
        attempts = int(result.get("attempts") or self._last_record_attempts or 1)
        entry = {
            "record_id": str(result.get("record_id") or record_id or self._record_id(record)),
            "status": self._terminal_record_status(raw_status),
            "raw_status": raw_status,
            "reason": result.get("reason"),
            "attempts": attempts,
            "retried": bool(result.get("retried") or attempts > 1),
            "stage": self.current_stage,
        }
        if result.get("details") is not None:
            entry["details"] = redact_value(result.get("details"), max_chars=1000)
        if result.get("evidence") is not None:
            entry["evidence"] = redact_value(result.get("evidence"), max_chars=1000)
        if self._pending_record_evidence:
            entry["evidence_events"] = list(self._pending_record_evidence)
        self.result.data.setdefault("records", []).append(entry)
        if self._resume_ledger:
            ledger_entry = self._resume_ledger.record_item(
                workflow=self.name,
                record_id=entry["record_id"],
                status=entry["status"],
                stage=entry.get("stage"),
                idempotency_key=result.get("idempotency_key"),
                external_reference_id=result.get("external_reference_id"),
                evidence_path=result.get("evidence_path"),
                details={
                    "reason": entry.get("reason"),
                    "attempts": entry.get("attempts"),
                    "retried": entry.get("retried"),
                },
            )
            self.result.data.setdefault("resume_ledger_entries", []).append(ledger_entry)
        self._write_record(entry)
        self._timeline(
            f"record.{entry['status']}",
            status=entry["status"],
            phase=entry.get("stage"),
            record_id=entry["record_id"],
            failure_kind="record_failed" if entry["status"] == "failed" else None,
            message=entry.get("reason"),
        )
        return entry

    def _refresh_record_summary(self) -> dict:
        records = self.result.data.setdefault("records", [])
        status_counts: Dict[str, int] = {}
        for record in records:
            status = str(record.get("status", "unknown"))
            status_counts[status] = status_counts.get(status, 0) + 1

        terminal_records = len(records)
        counted_terminal = (
            self.result.processed_records
            + self.result.failed_records
            + self.result.skipped_records
        )
        summary = {
            "total": self.result.total_records,
            "passed": self.result.processed_records,
            "failed": self.result.failed_records,
            "skipped": self.result.skipped_records,
            "retried": self.result.retried_records,
            "needs_review": status_counts.get("needs_review", 0),
            "terminal_records": terminal_records,
            "unprocessed": max(self.result.total_records - terminal_records, 0),
            "status_counts": status_counts,
            "reconciled": (
                terminal_records == counted_terminal
                and terminal_records == self.result.total_records
            ),
        }
        self.result.data["record_summary"] = summary
        return summary

    def _build_resume_ledger(self) -> Optional[ResumeLedger]:
        variables = getattr(self.config, "variables", {}) or {}
        path = variables.get("resume_ledger_path")
        if not path:
            return None
        return ResumeLedger(path)

    def _start_live_run(self) -> None:
        timestamp = self.result.start_time or datetime.now()
        self._run_id = f"{self.name}_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}"
        variables = getattr(self.config, "variables", {}) or {}
        self._run_dir = Path(str(variables.get("runs_dir") or "runs")) / self._run_id
        self._run_dir.mkdir(parents=True, exist_ok=True)
        self.result.data["run_id"] = self._run_id
        self.result.data["run_dir"] = str(self._run_dir)
        self._timeline("run.started", status="running")
        self._write_manifest("running")


    def _timeline(self, event: str, **fields: Any) -> None:
        if not self._run_dir or not self._run_id:
            return
        self._timeline_event_id += 1
        entry = {
            "event_id": self._timeline_event_id,
            "timestamp": utc_now_iso(),
            "run_id": self._run_id,
            "workflow": self.name,
            "event": event,
        }
        entry.update({key: value for key, value in fields.items() if value is not None})
        with (self._run_dir / "timeline.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(redact_value(entry), default=str) + "\n")

    def _write_record(self, entry: dict) -> None:
        if not self._run_dir or not self._run_id:
            return
        record = {
            "schema_version": 1,
            "run_id": self._run_id,
            "workflow": self.name,
            "record_id": entry.get("record_id"),
            "status": entry.get("status"),
            "failed_step": entry.get("stage") if entry.get("status") == "failed" else None,
            "failure_kind": "record_failed" if entry.get("status") == "failed" else None,
            "retry_count": max(int(entry.get("attempts") or 1) - 1, 0),
            "safe_retry": False,
            "timestamp": utc_now_iso(),
            "finished_at": utc_now_iso(),
        }
        with (self._run_dir / "records.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(redact_value(record), default=str) + "\n")

    def _write_manifest(self, status: str, *, finished: bool = False) -> None:
        if not self._run_dir or not self._run_id:
            return
        summary = {
            "total_steps": len(self.result.steps),
            "passed_steps": sum(1 for step in self.result.steps if step.status == StepStatus.PASSED),
            "failed_steps": sum(1 for step in self.result.steps if step.status == StepStatus.FAILED),
            "total_records": self.result.total_records,
            "passed_records": self.result.processed_records,
            "failed_records": self.result.failed_records,
            "skipped_records": self.result.skipped_records,
        }
        manifest = {
            "schema_version": 1,
            "run_id": self._run_id,
            "workflow": self.name,
            "workflow_path": None,
            "status": status,
            "started_at": self.result.start_time.isoformat() if self.result.start_time else None,
            "finished_at": self.result.end_time.isoformat() if finished and self.result.end_time else None,
            "duration_ms": self.result.duration_ms if finished else None,
            "report": "report.html",
            "timeline": "timeline.jsonl",
            "records": "records.jsonl" if (self._run_dir / "records.jsonl").exists() else None,
            "run_directory": str(self._run_dir.resolve()),
            "redaction": {"status": "passed"},
            "summary": summary,
        }
        write_json(self._run_dir / "run_manifest.json", manifest)

    def _write_live_report(self) -> None:
        if not self._run_dir:
            return
        report = {
            "manifest": read_json(self._run_dir / "run_manifest.json"),
            "result": self.result.to_dict(),
        }
        write_json(self._run_dir / "report.json", report)
        def cell(value: Any) -> str:
            return html.escape(str(redact_value(value) if value is not None else ""))

        rows = "".join(
            "<tr>"
            f"<td>{cell(step.name)}</td>"
            f"<td>{cell(step.status.value)}</td>"
            f"<td>{step.duration_ms:.0f}</td>"
            f"<td>{cell(step.error_message)}</td>"
            "</tr>"
            for step in self.result.steps
        )
        (self._run_dir / "report.html").write_text(
            "<!doctype html><html><head><meta charset='utf-8'><title>RPA Workflow Run</title>"
            "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:32px}"
            "table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px}</style></head><body>"
            f"<h1>{cell(self.name)}</h1><p>Status: {cell(self.result.status.value)}</p>"
            f"<p>Records: {self.result.processed_records}/{self.result.total_records} passed</p>"
            "<table><tr><th>Step</th><th>Status</th><th>ms</th><th>Error</th></tr>"
            f"{rows}</table></body></html>",
            encoding="utf-8",
        )
