"""Background job registry and lifecycle manager (@deepseek-ai/dsh-jobs-local & @deepseek-ai/dsh-tool-jobs).

Provides owner-scoped background process spawning, non-blocking stdout/stderr
capture, status querying (`job_list`), incremental output reading (`job_output`),
and recursive process tree termination (`job_kill` via Windows `taskkill /F /T`).
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .policy import PolicyChecker, SandboxPolicy
from .windows_compat import build_shell_command


class JobStatus(str, Enum):
    """Lifecycle states of a background job."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


class JobSummary(BaseModel):
    """Serializable summary of a background job."""

    job_id: str
    owner_session_id: str
    command: str
    cwd: str
    status: JobStatus
    pid: int | None = None
    exit_code: int | None = None
    started_at: float
    ended_at: float | None = None
    stdout_chars: int = 0
    stderr_chars: int = 0


class JobOutputSnapshot(BaseModel):
    """Incremental or full output snapshot of a background job."""

    job_id: str
    status: JobStatus
    exit_code: int | None = None
    stdout: str
    stderr: str
    duration_ms: float


class _LiveJob:
    """Internal handle for a running or finished background subprocess."""

    def __init__(
        self,
        job_id: str,
        owner_session_id: str,
        command: str,
        cwd: Path,
        proc: subprocess.Popen[str],
    ):
        self.job_id = job_id
        self.owner_session_id = owner_session_id
        self.command = command
        self.cwd = cwd
        self.proc = proc
        self.started_at = time.time()
        self.ended_at: float | None = None
        self.killed = False
        self._stdout_chunks: list[str] = []
        self._stderr_chunks: list[str] = []
        self._lock = threading.Lock()

        self._t_out = threading.Thread(
            target=self._drain_stream, args=(proc.stdout, self._stdout_chunks), daemon=True
        )
        self._t_err = threading.Thread(
            target=self._drain_stream, args=(proc.stderr, self._stderr_chunks), daemon=True
        )
        self._t_out.start()
        self._t_err.start()

    def _drain_stream(self, stream: Any, sink: list[str]) -> None:
        if stream is None:
            return
        try:
            for line in iter(stream.readline, ""):
                if not line:
                    break
                with self._lock:
                    sink.append(line)
        except Exception:
            pass
        finally:
            try:
                stream.close()
            except Exception:
                pass

    @property
    def status(self) -> JobStatus:
        rc = self.proc.poll()
        if rc is None:
            return JobStatus.RUNNING
        if self.ended_at is None:
            self.ended_at = time.time()
        if self.killed:
            return JobStatus.KILLED
        return JobStatus.COMPLETED if rc == 0 else JobStatus.FAILED

    def get_stdout(self) -> str:
        with self._lock:
            return "".join(self._stdout_chunks)

    def get_stderr(self) -> str:
        with self._lock:
            return "".join(self._stderr_chunks)

    def summary(self) -> JobSummary:
        st = self.status
        out_str = self.get_stdout()
        err_str = self.get_stderr()
        return JobSummary(
            job_id=self.job_id,
            owner_session_id=self.owner_session_id,
            command=self.command,
            cwd=str(self.cwd),
            status=st,
            pid=self.proc.pid,
            exit_code=self.proc.poll(),
            started_at=self.started_at,
            ended_at=self.ended_at,
            stdout_chars=len(out_str),
            stderr_chars=len(err_str),
        )


class BackgroundJobManager:
    """Process-local background job registry with owner session isolation."""

    def __init__(
        self,
        workspace_root: str | Path,
        default_policy: SandboxPolicy = SandboxPolicy.WORKSPACE_WRITE,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.default_policy = default_policy
        self._jobs: dict[str, _LiveJob] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _kill_process_tree(pid: int) -> None:
        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    timeout=5.0,
                    check=False,
                )
            except Exception:
                pass
        else:
            try:
                os.kill(pid, 9)
            except (OSError, ProcessLookupError):
                pass

    def start_job(
        self,
        command: str,
        owner_session_id: str = "default",
        cwd: str | Path | None = None,
        policy: SandboxPolicy | None = None,
        env: dict[str, str] | None = None,
        shell: str | None = None,
    ) -> JobSummary:
        """Spawn a command in the background under sandbox policy and return its JobSummary."""
        active_policy = policy or self.default_policy
        checker = PolicyChecker(policy=active_policy, workspace_root=self.workspace_root)
        target_cwd = checker.validate_working_directory(cwd)
        checker.validate_command(command)

        argv, _ = build_shell_command(command, shell=shell)
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        proc = subprocess.Popen(
            argv,
            cwd=str(target_cwd),
            env=merged_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )

        job_id = f"job_{uuid.uuid4().hex[:8]}"
        live_job = _LiveJob(
            job_id=job_id,
            owner_session_id=owner_session_id,
            command=command,
            cwd=target_cwd,
            proc=proc,
        )
        with self._lock:
            self._jobs[job_id] = live_job
        return live_job.summary()

    def list_jobs(self, owner_session_id: str | None = None) -> list[JobSummary]:
        """List all registered jobs, optionally filtered by owner session."""
        with self._lock:
            jobs = list(self._jobs.values())
        if owner_session_id is not None:
            jobs = [j for j in jobs if j.owner_session_id == owner_session_id]
        return [j.summary() for j in jobs]

    def get_job_output(self, job_id: str, wait_timeout: float = 0.0) -> JobOutputSnapshot:
        """Read current stdout/stderr and status for a background job."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"Unknown background job_id: {job_id}")

        if wait_timeout > 0 and job.status == JobStatus.RUNNING:
            try:
                job.proc.wait(timeout=wait_timeout)
            except subprocess.TimeoutExpired:
                pass
            # Allow reader threads a brief moment to flush remaining lines
            time.sleep(0.02)

        st = job.status
        end_t = job.ended_at or time.time()
        return JobOutputSnapshot(
            job_id=job.job_id,
            status=st,
            exit_code=job.proc.poll(),
            stdout=job.get_stdout(),
            stderr=job.get_stderr(),
            duration_ms=round((end_t - job.started_at) * 1000.0, 2),
        )

    def kill_job(self, job_id: str) -> JobSummary:
        """Terminate a running background job and its process tree."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"Unknown background job_id: {job_id}")

        if job.proc.poll() is None:
            job.killed = True
            self._kill_process_tree(job.proc.pid)
            try:
                job.proc.kill()
            except Exception:
                pass
            try:
                job.proc.wait(timeout=2.0)
            except Exception:
                pass
            job.ended_at = time.time()

        return job.summary()

    def cleanup_all(self) -> None:
        """Kill all running jobs managed by this instance."""
        with self._lock:
            job_ids = list(self._jobs.keys())
        for jid in job_ids:
            try:
                self.kill_job(jid)
            except Exception:
                pass
