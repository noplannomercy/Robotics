from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from models import Job, JobStatus

if TYPE_CHECKING:
    import asyncpg


class JobStore(ABC):
    @abstractmethod
    async def create(self, asset_type: str, file_name: str, source_hash: str, **kwargs) -> Job: ...

    @abstractmethod
    async def get(self, job_id: str) -> Job | None: ...

    @abstractmethod
    async def get_by_hash(self, source_hash: str) -> Job | None: ...

    @abstractmethod
    async def update_status(self, job_id: str, status: JobStatus) -> None: ...

    @abstractmethod
    async def save_result(self, job_id: str, result: str) -> None: ...

    @abstractmethod
    async def save_error(self, job_id: str, error: str) -> None: ...

    @abstractmethod
    async def increment_attempts(self, job_id: str) -> None: ...

    @abstractmethod
    async def list_jobs(self, page: int, size: int, status: str | None, asset_type: str | None) -> tuple[list[dict], int]: ...

    @abstractmethod
    async def delete(self, job_id: str) -> None: ...

    @abstractmethod
    async def count_by_status(self, statuses: list[str]) -> dict[str, int]: ...

    @abstractmethod
    async def get_stats(self) -> dict: ...


class InMemoryJobStore(JobStore):
    def __init__(self):
        self._jobs: dict[str, Job] = {}

    async def create(self, asset_type: str, file_name: str, source_hash: str, **kwargs) -> Job:
        job = Job(
            id=str(uuid.uuid4()),
            status=JobStatus.QUEUED,
            asset_type=asset_type,
            file_name=file_name,
            source_hash=source_hash,
            **kwargs,
        )
        self._jobs[job.id] = job
        return job

    async def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def get_by_hash(self, source_hash: str) -> Job | None:
        for job in self._jobs.values():
            if job.source_hash == source_hash:
                return job
        return None

    async def update_status(self, job_id: str, status: JobStatus) -> None:
        if job_id in self._jobs:
            job = self._jobs[job_id]
            self._jobs[job_id] = job.model_copy(update={
                "status": status,
                "started_at": datetime.now(timezone.utc) if status == JobStatus.PROCESSING else job.started_at,
            })

    async def save_result(self, job_id: str, result: str) -> None:
        if job_id in self._jobs:
            job = self._jobs[job_id]
            self._jobs[job_id] = job.model_copy(update={
                "status": JobStatus.COMPLETED,
                "result": result,
                "completed_at": datetime.now(timezone.utc),
            })

    async def save_error(self, job_id: str, error: str) -> None:
        if job_id in self._jobs:
            job = self._jobs[job_id]
            self._jobs[job_id] = job.model_copy(update={
                "status": JobStatus.FAILED,
                "error": error,
                "completed_at": datetime.now(timezone.utc),
            })

    async def increment_attempts(self, job_id: str) -> None:
        if job_id in self._jobs:
            job = self._jobs[job_id]
            self._jobs[job_id] = job.model_copy(update={"attempts": job.attempts + 1})

    async def list_jobs(self, page: int = 1, size: int = 20, status: str | None = None, asset_type: str | None = None) -> tuple[list[dict], int]:
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        if asset_type:
            jobs = [j for j in jobs if j.asset_type == asset_type]
        total = len(jobs)
        start = (page - 1) * size
        sliced = jobs[start:start + size]
        return [j.model_dump() for j in sliced], total

    async def delete(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)

    async def count_by_status(self, statuses: list[str]) -> dict[str, int]:
        result = {s: 0 for s in statuses}
        for job in self._jobs.values():
            if job.status in result:
                result[job.status] += 1
        return result

    async def get_stats(self) -> dict:
        jobs = list(self._jobs.values())
        total = len(jobs)

        by_status: dict[str, int] = {"queued": 0, "processing": 0, "completed": 0, "failed": 0}
        by_asset_type: dict[str, int] = {}
        retry_count = 0
        processing_times: list[float] = []
        recent_failures: list[dict] = []

        for job in jobs:
            status_key = str(job.status)
            by_status[status_key] = by_status.get(status_key, 0) + 1
            by_asset_type[job.asset_type] = by_asset_type.get(job.asset_type, 0) + 1
            if job.attempts > 1:
                retry_count += 1
            if (
                str(job.status) == "completed"
                and job.started_at is not None
                and job.completed_at is not None
            ):
                duration = (job.completed_at - job.started_at).total_seconds()
                processing_times.append(duration)
            if str(job.status) == "failed":
                recent_failures.append({
                    "job_id": job.id,
                    "file_name": job.file_name,
                    "error": job.error,
                    "failed_at": str(job.completed_at) if job.completed_at else None,
                })

        recent_failures.sort(key=lambda x: x["failed_at"] or "", reverse=True)

        return {
            "total": total,
            "by_status": by_status,
            "by_asset_type": by_asset_type,
            "success_rate": round(by_status.get("completed", 0) / total * 100, 1) if total > 0 else 0.0,
            "avg_processing_sec": round(sum(processing_times) / len(processing_times), 1) if processing_times else None,
            "retry_rate": round(retry_count / total * 100, 1) if total > 0 else 0.0,
            "recent_failures": recent_failures[:5],
        }


class PostgresJobStore(JobStore):
    def __init__(self, pool: "asyncpg.Pool"):
        self._pool = pool

    def _row_to_job(self, row: dict) -> Job:
        return Job(
            id=str(row["job_id"]),
            status=JobStatus(row["status"]),
            asset_type=row["asset_type"],
            file_name=row["file_name"],
            file_size=row["file_size"],
            source_hash=row["source_hash"],
            source_bytes=row.get("source_bytes"),
            result=row["result"],
            error=row["error"],
            attempts=row["attempts"],
            callback_url=row["callback_url"],
            requested_by=row["requested_by"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            rag_mode=row.get("rag_mode") or "mix",
        )

    async def create(self, asset_type: str, file_name: str, source_hash: str, **kwargs) -> Job:
        job_id = str(uuid.uuid4())
        row = await self._pool.fetchrow(
            """INSERT INTO rdoc_job
               (job_id, asset_type, file_name, file_size, source_hash,
                source_bytes, callback_url, requested_by, rag_mode)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
               RETURNING *""",
            job_id, asset_type, file_name,
            kwargs.get("file_size"), source_hash,
            kwargs.get("source_bytes"),
            kwargs.get("callback_url"), kwargs.get("requested_by"),
            kwargs.get("rag_mode", "mix"),
        )
        return self._row_to_job(dict(row))

    async def get(self, job_id: str) -> Job | None:
        try:
            row = await self._pool.fetchrow(
                "SELECT * FROM rdoc_job WHERE job_id = $1", job_id
            )
        except Exception:
            return None
        return self._row_to_job(dict(row)) if row else None

    async def get_by_hash(self, source_hash: str) -> Job | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM rdoc_job WHERE source_hash = $1", source_hash
        )
        return self._row_to_job(dict(row)) if row else None

    async def update_status(self, job_id: str, status: JobStatus) -> None:
        if status == JobStatus.PROCESSING:
            await self._pool.execute(
                "UPDATE rdoc_job SET status = $1, started_at = now() WHERE job_id = $2",
                status, job_id,
            )
        else:
            await self._pool.execute(
                "UPDATE rdoc_job SET status = $1 WHERE job_id = $2",
                status, job_id,
            )

    async def save_result(self, job_id: str, result: str) -> None:
        await self._pool.execute(
            "UPDATE rdoc_job SET status = 'completed', result = $1, completed_at = now() WHERE job_id = $2",
            result, job_id,
        )

    async def save_error(self, job_id: str, error: str) -> None:
        await self._pool.execute(
            "UPDATE rdoc_job SET status = 'failed', error = $1, completed_at = now() WHERE job_id = $2",
            error, job_id,
        )

    async def increment_attempts(self, job_id: str) -> None:
        await self._pool.execute(
            "UPDATE rdoc_job SET attempts = attempts + 1 WHERE job_id = $1", job_id
        )

    async def list_jobs(self, page: int = 1, size: int = 20, status: str | None = None, asset_type: str | None = None) -> tuple[list[dict], int]:
        conditions = []
        params: list = []
        idx = 1
        if status:
            conditions.append(f"status = ${idx}")
            params.append(status)
            idx += 1
        if asset_type:
            conditions.append(f"asset_type = ${idx}")
            params.append(asset_type)
            idx += 1
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        total = await self._pool.fetchval(f"SELECT COUNT(*) FROM rdoc_job {where}", *params)
        offset = (page - 1) * size
        rows = await self._pool.fetch(
            f"SELECT * FROM rdoc_job {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}",
            *params, size, offset,
        )
        return [dict(r) for r in rows], total

    async def delete(self, job_id: str) -> None:
        await self._pool.execute("DELETE FROM rdoc_job WHERE job_id = $1", job_id)

    async def count_by_status(self, statuses: list[str]) -> dict[str, int]:
        rows = await self._pool.fetch(
            "SELECT status, COUNT(*) as cnt FROM rdoc_job "
            "WHERE status = ANY($1) GROUP BY status",
            statuses,
        )
        result = {s: 0 for s in statuses}
        for r in rows:
            result[r["status"]] = r["cnt"]
        return result

    async def get_stats(self) -> dict:
        total = await self._pool.fetchval("SELECT COUNT(*) FROM rdoc_job") or 0

        by_status_rows = await self._pool.fetch(
            "SELECT status, COUNT(*) as cnt FROM rdoc_job GROUP BY status"
        )
        by_status: dict[str, int] = {"queued": 0, "processing": 0, "completed": 0, "failed": 0}
        for r in by_status_rows:
            by_status[r["status"]] = r["cnt"]

        by_type_rows = await self._pool.fetch(
            "SELECT asset_type, COUNT(*) as cnt FROM rdoc_job GROUP BY asset_type"
        )
        by_asset_type = {r["asset_type"]: r["cnt"] for r in by_type_rows}

        avg_raw = await self._pool.fetchval(
            "SELECT EXTRACT(EPOCH FROM AVG(completed_at - started_at)) "
            "FROM rdoc_job WHERE status = 'completed' "
            "AND started_at IS NOT NULL AND completed_at IS NOT NULL"
        )

        retry_count = await self._pool.fetchval(
            "SELECT COUNT(*) FROM rdoc_job WHERE attempts > 1"
        ) or 0

        failure_rows = await self._pool.fetch(
            "SELECT job_id, file_name, error, completed_at FROM rdoc_job "
            "WHERE status = 'failed' ORDER BY completed_at DESC LIMIT 5"
        )
        recent_failures = [
            {
                "job_id": str(r["job_id"]),
                "file_name": r["file_name"],
                "error": r["error"],
                "failed_at": str(r["completed_at"]) if r["completed_at"] else None,
            }
            for r in failure_rows
        ]

        completed = by_status.get("completed", 0)
        return {
            "total": total,
            "by_status": by_status,
            "by_asset_type": by_asset_type,
            "success_rate": round(completed / total * 100, 1) if total > 0 else 0.0,
            "avg_processing_sec": round(float(avg_raw), 1) if avg_raw is not None else None,
            "retry_rate": round(retry_count / total * 100, 1) if total > 0 else 0.0,
            "recent_failures": recent_failures,
        }


class PromptStore:
    def __init__(self, pool: "asyncpg.Pool"):
        self._pool = pool

    async def get_active(self, asset_type: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM rdoc_prompt WHERE asset_type = $1 AND is_active = TRUE",
            asset_type,
        )
        return dict(row) if row else None

    async def seed_if_empty(self, asset_type: str, default_text: str) -> None:
        exists = await self._pool.fetchval(
            "SELECT COUNT(*) FROM rdoc_prompt WHERE asset_type = $1", asset_type
        )
        if exists == 0:
            await self._pool.execute(
                "INSERT INTO rdoc_prompt (asset_type, version, text, is_active) VALUES ($1, 1, $2, TRUE)",
                asset_type, default_text,
            )

    async def create_version(self, asset_type: str, text: str) -> dict:
        max_ver = await self._pool.fetchval(
            "SELECT MAX(version) FROM rdoc_prompt WHERE asset_type = $1", asset_type
        )
        new_ver = (max_ver or 0) + 1
        await self._pool.execute(
            "UPDATE rdoc_prompt SET is_active = FALSE WHERE asset_type = $1 AND is_active = TRUE",
            asset_type,
        )
        row = await self._pool.fetchrow(
            "INSERT INTO rdoc_prompt (asset_type, version, text, is_active) VALUES ($1, $2, $3, TRUE) RETURNING *",
            asset_type, new_ver, text,
        )
        return dict(row)

    async def list_versions(self, asset_type: str) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT id, asset_type, version, is_active, created_at "
            "FROM rdoc_prompt WHERE asset_type = $1 ORDER BY version DESC",
            asset_type,
        )
        return [dict(r) for r in rows]

    async def get_version(self, asset_type: str, version: int) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM rdoc_prompt WHERE asset_type = $1 AND version = $2",
            asset_type, version,
        )
        return dict(row) if row else None


class InMemoryPromptStore:
    def __init__(self):
        self._data: dict[str, list[dict]] = {}
        self._next_id = 1

    async def get_active(self, asset_type: str) -> dict | None:
        for entry in self._data.get(asset_type, []):
            if entry["is_active"]:
                return dict(entry)
        return None

    async def seed_if_empty(self, asset_type: str, default_text: str) -> None:
        if self._data.get(asset_type):
            return
        await self.create_version(asset_type, default_text)

    async def create_version(self, asset_type: str, text: str) -> dict:
        versions = self._data.setdefault(asset_type, [])
        for entry in versions:
            entry["is_active"] = False
        new_ver = (max((e["version"] for e in versions), default=0)) + 1
        entry = {"id": self._next_id, "asset_type": asset_type, "version": new_ver, "text": text, "is_active": True}
        self._next_id += 1
        versions.insert(0, entry)
        return dict(entry)

    async def list_versions(self, asset_type: str) -> list[dict]:
        return [
            {
                "id": e["id"],
                "asset_type": e["asset_type"],
                "version": e["version"],
                "is_active": e["is_active"],
                "created_at": None,
            }
            for e in self._data.get(asset_type, [])
        ]

    async def get_version(self, asset_type: str, version: int) -> dict | None:
        for e in self._data.get(asset_type, []):
            if e["version"] == version:
                return dict(e)
        return None
