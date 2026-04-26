"""
Job queue and scheduling for RPA workflows.
Supports priority queues, scheduling, and execution history.
"""

import asyncio
import heapq
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import uuid


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPriority(Enum):
    LOW = 0
    NORMAL = 5
    HIGH = 10
    CRITICAL = 15


@dataclass(order=True)
class Job:
    sort_index: int = field(init=False)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    priority: JobPriority = JobPriority.NORMAL
    workflow_name: str = ""
    payload: dict = field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    error_message: Optional[str] = None
    result: dict = field(default_factory=dict)
    attempts: int = 0
    max_attempts: int = 3
    scheduled_at: Optional[datetime] = None

    def __post_init__(self):
        self.sort_index = -self.priority.value

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "priority": self.priority.name,
            "workflow_name": self.workflow_name,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
            "attempts": self.attempts,
        }


@dataclass
class JobQueue:
    max_concurrent: int = 4
    store_path: Optional[str] = None
    _queue: List[Job] = field(default_factory=list, init=False)
    _history: List[Job] = field(default_factory=list, init=False)
    _running: Dict[str, Job] = field(default_factory=dict, init=False)
    _handlers: Dict[str, Callable] = field(default_factory=dict, init=False)

    def enqueue(self, job: Job) -> str:
        if job.id in {j.id for j in self._running}:
            raise ValueError(f"Job {job.id} is already running")
        heapq.heappush(self._queue, job)
        return job.id

    def dequeue(self) -> Optional[Job]:
        if not self._queue:
            return None
        return heapq.heappop(self._queue)

    def peek(self) -> Optional[Job]:
        return self._queue[0] if self._queue else None

    def size(self) -> int:
        return len(self._queue)

    def pending(self) -> List[Job]:
        return [j for j in self._queue if j.status == JobStatus.PENDING]

    def running_count(self) -> int:
        return len(self._running)

    def register_handler(self, workflow_name: str, handler: Callable):
        self._handlers[workflow_name] = handler

    async def process(self, max_jobs: Optional[int] = None) -> List[Job]:
        completed = []
        jobs_to_run = min(self.size(), max_jobs or self.size())

        for _ in range(jobs_to_run):
            job = self.dequeue()
            if not job:
                break

            job.status = JobStatus.RUNNING
            job.started_at = datetime.now()
            job.attempts += 1
            self._running[job.id] = job

            try:
                handler = self._handlers.get(job.workflow_name)
                if handler:
                    start = time.monotonic()
                    result = await handler(job.payload) if asyncio.iscoroutinefunction(handler) else handler(job.payload)
                    job.duration_ms = (time.monotonic() - start) * 1000
                    job.result = result or {}
                    job.status = JobStatus.COMPLETED
                else:
                    job.status = JobStatus.FAILED
                    job.error_message = f"No handler for workflow: {job.workflow_name}"
            except Exception as e:
                job.status = JobStatus.FAILED
                job.error_message = str(e)

                if job.attempts < job.max_attempts:
                    job.status = JobStatus.PENDING
                    self.enqueue(job)

            job.completed_at = datetime.now()
            self._running.pop(job.id, None)
            self._history.append(job)
            completed.append(job)

        return completed

    def get_history(self, status: Optional[JobStatus] = None, limit: int = 50) -> List[Job]:
        history = self._history
        if status:
            history = [j for j in history if j.status == status]
        return sorted(history, key=lambda j: j.created_at, reverse=True)[:limit]

    def cancel(self, job_id: str):
        remaining = []
        for job in self._queue:
            if job.id == job_id:
                job.status = JobStatus.CANCELLED
                self._history.append(job)
            else:
                remaining.append(job)
        self._queue = remaining
        heapq.heapify(self._queue)

    def clear_completed(self):
        self._history = [j for j in self._history if j.status != JobStatus.COMPLETED]
