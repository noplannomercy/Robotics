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
            result=row["result"],
            error=row["error"],
            attempts=row["attempts"],
            callback_url=row["callback_url"],
            requested_by=row["requested_by"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )

    async def create(self, asset_type: str, file_name: str, source_hash: str, **kwargs) -> Job:
        job_id = str(uuid.uuid4())
        row = await self._pool.fetchrow(
            """INSERT INTO rdoc_job
               (job_id, asset_type, file_name, file_size, source_hash, callback_url, requested_by)
               VALUES ($1, $2, $3, $4, $5, $6, $7)
               RETURNING *""",
            job_id, asset_type, file_name,
            kwargs.get("file_size"), source_hash,
            kwargs.get("callback_url"), kwargs.get("requested_by"),
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
