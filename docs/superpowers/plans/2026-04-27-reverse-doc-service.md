# Reverse-Doc Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Oracle 자산(PL/SQL, 딕셔너리, ERD, 정책)을 v2 canonical 식별자 markdown으로 역문서화하는 비동기 FastAPI 서비스 구축

**Architecture:** Forge 패턴 그대로 적용 — FastAPI + asyncpg + pydantic-settings + async job store + _safe_process 래퍼 + TDD. LightRAG는 context 조회(read-only)만, insert는 ingestion-router 담당. DB는 Hostinger 원격 PostgreSQL 사용.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, httpx, asyncpg, pydantic-settings, pytest, pytest-asyncio

---

## File Map

| 파일 | 역할 | Task |
|------|------|------|
| `requirements.txt` | 의존성 | 1 |
| `.env.example` | 환경변수 템플릿 | 1 |
| `config.py` | 환경변수 로드 | 1 |
| `models.py` | Pydantic 모델 (Job, JobStatus, AssetType) | 2 |
| `schema.sql` | DB DDL (rdoc_job, rdoc_prompt) | 3 |
| `job_store.py` | JobStore ABC + InMemoryJobStore + PostgresJobStore + PromptStore | 3 |
| `auth.py` | API 키 인증 dependency | 4 |
| `validator.py` | 역문서 품질 검증 check 1-4 | 5 |
| `llm_client.py` | OpenAI-compatible 비동기 LLM 클라이언트 | 6 |
| `rag_client.py` | LightRAG REST API 쿼리 전용 | 7 |
| `prompts.py` | PromptStore 초기 시드 콘텐츠 | 8 |
| `callback.py` | ingestion-router 콜백 전송 | 9 |
| `processor.py` | 역문서화 파이프라인 오케스트레이터 | 10 |
| `worker.py` | 비동기 워커 루프 + _safe_process | 11 |
| `app.py` | FastAPI 앱 + 5개 엔드포인트 | 12 |
| `admin.py` | 관리 API 2개 엔드포인트 | 13 |
| `Dockerfile` | Docker 빌드 | 14 |
| `tests/test_config.py` | config 단위 테스트 | 1 |
| `tests/test_models.py` | models 단위 테스트 | 2 |
| `tests/test_job_store.py` | job_store 단위 테스트 | 3 |
| `tests/test_validator.py` | validator 단위 테스트 | 5 |
| `tests/test_llm_client.py` | llm_client 단위 테스트 | 6 |
| `tests/test_rag_client.py` | rag_client 단위 테스트 | 7 |
| `tests/test_callback.py` | callback 단위 테스트 | 9 |
| `tests/test_processor.py` | processor 단위 테스트 | 10 |
| `tests/test_app.py` | app 엔드포인트 테스트 | 12 |
| `tests/test_e2e.py` | Mock E2E 전체 흐름 테스트 | 15 |

---

### Task 1: 프로젝트 셋업 + config.py

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `config.py`
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: requirements.txt 작성**

```
# 코어
fastapi>=0.115.0
uvicorn>=0.30.0
httpx>=0.27.0
pydantic-settings>=2.0.0
python-multipart>=0.0.6

# DB
asyncpg>=0.29.0

# 테스트
pytest>=8.0.0
pytest-asyncio>=0.24.0
```

- [ ] **Step 2: .env.example 작성**

```
# LLM (OpenAI-compatible)
LLM_URL=http://localhost:11434/v1/chat/completions
LLM_MODEL=qwen2.5:14b
LLM_API_KEY=
LLM_TIMEOUT=120
LLM_CONCURRENCY=3

# LightRAG (쿼리 전용)
LIGHTRAG_URL=http://localhost:8080
LIGHTRAG_API_KEY=
RAG_TIMEOUT=60

# 서비스
DATABASE_URL=postgresql://user:pass@host:5432/dbname
ADMIN_API_KEY=
MAX_FILE_SIZE_KB=200
PORT=8004
HOST=0.0.0.0
```

- [ ] **Step 3: tests/__init__.py 생성 (빈 파일)**

- [ ] **Step 4: 테스트 작성 — config.py**

```python
# tests/test_config.py
import pytest
from config import Config


def test_config_defaults():
    config = Config()
    assert config.llm_url == "http://localhost:11434/v1/chat/completions"
    assert config.llm_model == "qwen2.5:14b"
    assert config.llm_api_key == ""
    assert config.llm_timeout == 120
    assert config.llm_concurrency == 3
    assert config.lightrag_url == "http://localhost:8080"
    assert config.rag_timeout == 60
    assert config.database_url == ""
    assert config.admin_api_key == ""
    assert config.max_file_size_kb == 200
    assert config.port == 8004


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("LLM_URL", "http://custom:8080/v1/chat/completions")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("LLM_TIMEOUT", "60")
    monkeypatch.setenv("LLM_CONCURRENCY", "5")
    monkeypatch.setenv("RAG_TIMEOUT", "30")
    monkeypatch.setenv("PORT", "9000")
    config = Config()
    assert config.llm_url == "http://custom:8080/v1/chat/completions"
    assert config.llm_model == "gpt-4o"
    assert config.llm_timeout == 60
    assert config.llm_concurrency == 5
    assert config.rag_timeout == 30
    assert config.port == 9000
```

- [ ] **Step 5: 테스트 실패 확인**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 6: config.py 구현**

```python
# config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    # LLM
    llm_url: str = "http://localhost:11434/v1/chat/completions"
    llm_model: str = "qwen2.5:14b"
    llm_api_key: str = ""
    llm_timeout: int = 120
    llm_concurrency: int = 3

    # LightRAG (쿼리 전용)
    lightrag_url: str = "http://localhost:8080"
    lightrag_api_key: str = ""
    rag_timeout: int = 60

    # 서비스
    database_url: str = ""
    admin_api_key: str = ""
    max_file_size_kb: int = 200
    host: str = "0.0.0.0"
    port: int = 8004

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `python -m pytest tests/test_config.py -v`
Expected: 2 passed

- [ ] **Step 8: 커밋**

```bash
git init
git add requirements.txt .env.example config.py tests/__init__.py tests/test_config.py
git commit -m "feat: project setup + config"
```

---

### Task 2: models.py

**Files:**
- Create: `models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_models.py
from datetime import datetime, timezone
import pytest
from models import AssetType, Job, JobStatus


def test_job_status_values():
    assert JobStatus.QUEUED == "queued"
    assert JobStatus.PROCESSING == "processing"
    assert JobStatus.COMPLETED == "completed"
    assert JobStatus.FAILED == "failed"


def test_asset_type_values():
    assert AssetType.PLSQL == "plsql"
    assert AssetType.DICTIONARY == "dictionary"
    assert AssetType.ERD == "erd"
    assert AssetType.POLICY == "policy"


def test_job_creation():
    job = Job(
        id="test-id",
        status=JobStatus.QUEUED,
        asset_type=AssetType.PLSQL,
        file_name="PKG_TEST.sql",
        source_hash="abc123",
    )
    assert job.id == "test-id"
    assert job.status == JobStatus.QUEUED
    assert job.result is None
    assert job.error is None
    assert job.attempts == 0
    assert isinstance(job.created_at, datetime)


def test_job_optional_fields():
    job = Job(
        id="x",
        status=JobStatus.COMPLETED,
        asset_type="plsql",
        file_name="f.sql",
        source_hash="h",
        result="# 역문서",
        callback_url="http://router/callback",
        requested_by="ingestion-router",
    )
    assert job.result == "# 역문서"
    assert job.callback_url == "http://router/callback"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'models'`

- [ ] **Step 3: models.py 구현**

```python
# models.py
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AssetType(StrEnum):
    PLSQL = "plsql"
    DICTIONARY = "dictionary"
    ERD = "erd"
    POLICY = "policy"


class Job(BaseModel):
    id: str
    status: JobStatus
    asset_type: str
    file_name: str
    file_size: int | None = None
    source_hash: str
    result: str | None = None
    error: str | None = None
    attempts: int = 0
    callback_url: str | None = None
    requested_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_models.py -v`
Expected: 4 passed

- [ ] **Step 5: 커밋**

```bash
git add models.py tests/test_models.py
git commit -m "feat: models (Job, JobStatus, AssetType)"
```

---

### Task 3: schema.sql + job_store.py

**Files:**
- Create: `schema.sql`
- Create: `job_store.py`
- Create: `tests/test_job_store.py`

- [ ] **Step 1: schema.sql 작성**

```sql
-- schema.sql
-- Reverse-Doc Service DB schema (rdoc_ 접두사)

CREATE TABLE IF NOT EXISTS rdoc_job (
    job_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_type   TEXT NOT NULL,
    file_name    TEXT NOT NULL,
    file_size    BIGINT,
    source_hash  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'queued',
    result       TEXT,
    error        TEXT,
    attempts     INT NOT NULL DEFAULT 0,
    callback_url TEXT,
    requested_by TEXT,
    created_at   TIMESTAMPTZ DEFAULT now(),
    started_at   TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rdoc_job_source_hash ON rdoc_job(source_hash);
CREATE INDEX IF NOT EXISTS idx_rdoc_job_status ON rdoc_job(status);
CREATE INDEX IF NOT EXISTS idx_rdoc_job_created ON rdoc_job(created_at DESC);

CREATE TABLE IF NOT EXISTS rdoc_prompt (
    id          SERIAL PRIMARY KEY,
    asset_type  TEXT NOT NULL,
    version     INT NOT NULL,
    text        TEXT NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rdoc_prompt_active
    ON rdoc_prompt(asset_type) WHERE is_active = TRUE;
```

- [ ] **Step 2: 테스트 작성 — InMemoryJobStore**

```python
# tests/test_job_store.py
import pytest
from models import JobStatus
from job_store import InMemoryJobStore, InMemoryPromptStore


@pytest.fixture
def store():
    return InMemoryJobStore()


@pytest.fixture
def prompt_store():
    return InMemoryPromptStore()


@pytest.mark.asyncio
async def test_create_and_get(store):
    job = await store.create(
        asset_type="plsql",
        file_name="PKG_TEST.sql",
        source_hash="hash1",
        file_size=1000,
        callback_url="http://cb",
        requested_by="test",
    )
    assert job.id is not None
    assert job.status == JobStatus.QUEUED
    assert job.source_hash == "hash1"

    fetched = await store.get(job.id)
    assert fetched is not None
    assert fetched.id == job.id


@pytest.mark.asyncio
async def test_get_nonexistent(store):
    result = await store.get("nonexistent-id")
    assert result is None


@pytest.mark.asyncio
async def test_update_status(store):
    job = await store.create(asset_type="plsql", file_name="f.sql", source_hash="h2")
    await store.update_status(job.id, JobStatus.PROCESSING)
    updated = await store.get(job.id)
    assert updated.status == JobStatus.PROCESSING
    assert updated.started_at is not None


@pytest.mark.asyncio
async def test_save_result(store):
    job = await store.create(asset_type="plsql", file_name="f.sql", source_hash="h3")
    await store.save_result(job.id, "# 역문서 내용")
    updated = await store.get(job.id)
    assert updated.status == JobStatus.COMPLETED
    assert updated.result == "# 역문서 내용"
    assert updated.completed_at is not None


@pytest.mark.asyncio
async def test_save_error(store):
    job = await store.create(asset_type="plsql", file_name="f.sql", source_hash="h4")
    await store.save_error(job.id, "LLM timeout")
    updated = await store.get(job.id)
    assert updated.status == JobStatus.FAILED
    assert updated.error == "LLM timeout"


@pytest.mark.asyncio
async def test_get_by_hash(store):
    job = await store.create(asset_type="plsql", file_name="f.sql", source_hash="unique-hash")
    found = await store.get_by_hash("unique-hash")
    assert found is not None
    assert found.id == job.id

    not_found = await store.get_by_hash("no-such-hash")
    assert not_found is None


@pytest.mark.asyncio
async def test_increment_attempts(store):
    job = await store.create(asset_type="plsql", file_name="f.sql", source_hash="h5")
    await store.increment_attempts(job.id)
    updated = await store.get(job.id)
    assert updated.attempts == 1


@pytest.mark.asyncio
async def test_prompt_store_seed_and_get(prompt_store):
    await prompt_store.seed_if_empty("plsql", "initial prompt text")
    result = await prompt_store.get_active("plsql")
    assert result is not None
    assert result["text"] == "initial prompt text"
    assert result["version"] == 1


@pytest.mark.asyncio
async def test_prompt_store_seed_idempotent(prompt_store):
    await prompt_store.seed_if_empty("plsql", "first")
    await prompt_store.seed_if_empty("plsql", "second")  # should not overwrite
    result = await prompt_store.get_active("plsql")
    assert result["text"] == "first"


@pytest.mark.asyncio
async def test_prompt_store_get_nonexistent(prompt_store):
    result = await prompt_store.get_active("nonexistent")
    assert result is None
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `python -m pytest tests/test_job_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'job_store'`

- [ ] **Step 4: job_store.py 구현**

```python
# job_store.py
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
        row = await self._pool.fetchrow(
            "SELECT * FROM rdoc_job WHERE job_id = $1", job_id
        )
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
            f"SELECT * FROM rdoc_job {where} ORDER BY created_at DESC LIMIT ${ idx} OFFSET ${idx + 1}",
            *params, size, offset,
        )
        return [dict(r) for r in rows], total


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
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_job_store.py -v`
Expected: 10 passed

- [ ] **Step 6: 커밋**

```bash
git add schema.sql job_store.py tests/test_job_store.py
git commit -m "feat: schema + job_store (InMemory + Postgres + PromptStore)"
```

---

### Task 4: auth.py

**Files:**
- Create: `auth.py`

(auth 테스트는 Task 12 test_app.py에서 통합 검증)

- [ ] **Step 1: auth.py 구현**

```python
# auth.py
from fastapi import Header, HTTPException

from config import Config


def verify_api_key(config: Config):
    """Admin API 키 인증 dependency. admin_api_key 미설정 시 인증 비활성."""
    def _verify(x_rdoc_key: str | None = Header(None)):
        if not config.admin_api_key:
            return None
        if x_rdoc_key != config.admin_api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return _verify
```

- [ ] **Step 2: 커밋**

```bash
git add auth.py
git commit -m "feat: auth (optional API key dependency)"
```

---

### Task 5: validator.py

**Files:**
- Create: `validator.py`
- Create: `tests/test_validator.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_validator.py
import pytest
from validator import validate, ValidationResult

# --- check 1: project identifier coverage ---

def test_check1_pass_all_identifiers_present():
    raw = "PROC_CREDIT_EVALUATION calls TBL_LOAN_APPLICATION"
    reverse = "PROC_CREDIT_EVALUATION은 TBL_LOAN_APPLICATION을 조회한다."
    result = validate(raw, reverse)
    assert result.passed is True


def test_check1_fail_missing_identifier():
    raw = "PROC_CREDIT_EVALUATION calls TBL_LOAN_APPLICATION and TBL_CREDIT_SCORE"
    reverse = "PROC_CREDIT_EVALUATION은 TBL_LOAN_APPLICATION을 조회한다."
    result = validate(raw, reverse)
    assert result.passed is False
    assert "TBL_CREDIT_SCORE" in result.feedback
    assert "check 1" in result.feedback


def test_check1_sql_keywords_excluded():
    # BEGIN, END, IF, EXCEPTION 등 SQL 키워드는 check 1에서 제외
    raw = "BEGIN IF x THEN END IF; EXCEPTION WHEN OTHERS"
    reverse = "이 프로시저는 조건 분기를 수행한다."
    result = validate(raw, reverse)
    assert result.passed is True  # SQL 키워드 누락으로 실패하면 안 됨


# --- check 2: canonical notation ---

def test_check2_pass_all_uppercase():
    raw = "PROC_TEST calls TBL_MASTER"
    reverse = "PROC_TEST는 TBL_MASTER를 조회한다."
    result = validate(raw, reverse)
    assert result.passed is True


def test_check2_fail_lowercase_identifier():
    raw = "PROC_TEST"
    reverse = "proc_test는 실행된다."
    result = validate(raw, reverse)
    assert result.passed is False
    assert "check 2" in result.feedback


# --- check 3: no standalone enum values ---

def test_check3_pass_enum_with_table_col():
    raw = "STATUS column set to APPROVED"
    reverse = "TBL_LOAN_APPLICATION.STATUS = 'APPROVED'로 변경한다."
    result = validate(raw, reverse)
    assert result.passed is True


def test_check3_fail_standalone_enum():
    raw = "STATUS column"
    reverse = "상태를 'REJECTED'로 변경한다."
    result = validate(raw, reverse)
    assert result.passed is False
    assert "check 3" in result.feedback


# --- check 4: no standalone column names ---

def test_check4_pass_dot_notation():
    raw = "PROC_TEST updates STATUS column"
    reverse = "PROC_TEST는 TBL_LOAN_APPLICATION.STATUS를 변경한다."
    result = validate(raw, reverse)
    assert result.passed is True


def test_check4_fail_standalone_column():
    raw = "PROC_TEST updates EVAL_TYPE column"
    reverse = "PROC_TEST는 EVAL_TYPE을 변경한다."
    result = validate(raw, reverse)
    assert result.passed is False
    assert "check 4" in result.feedback


# --- feedback format ---

def test_feedback_includes_all_failed_checks():
    raw = "PROC_A TBL_B"
    reverse = "proc_a 실행, 'DONE' 상태, EVAL_TYPE 변경"
    result = validate(raw, reverse)
    assert result.passed is False
    # feedback에 여러 check 실패가 모두 포함되어야 함
    assert "check 1" in result.feedback or "check 2" in result.feedback
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_validator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'validator'`

- [ ] **Step 3: validator.py 구현**

```python
# validator.py
import re
from dataclasses import dataclass

# 프로젝트 식별자 패턴 — SQL 키워드(BEGIN/END/IF 등) 제외
PROJECT_ID_RE = re.compile(r'\b(?:TBL|PROC|FUNC|PKG|SEQ|FK|PK)_[A-Z0-9_]+\b')

# 단독 enum 값 패턴: 앞이 '.' 또는 '=' 이 아닌 위치의 'UPPERCASE_VALUE'
STANDALONE_ENUM_RE = re.compile(r"(?<![.=\w])'([A-Z][A-Z0-9_]+)'")

# 단독 컬럼명 패턴: 프로젝트 prefix 없이 점 표기 없이 등장하는 대문자 식별자
# 앞에 '.' 이 없고, prefix(TBL_/PROC_ 등)가 없는 경우
STANDALONE_COL_RE = re.compile(r'(?<![.\w])\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b(?!\s*[=(\'_])')


@dataclass
class ValidationResult:
    passed: bool
    feedback: str | None = None


def validate(raw: str, reverse: str) -> ValidationResult:
    failures: list[str] = []

    # check 1: 프로젝트 식별자 누락 검사
    raw_ids = set(PROJECT_ID_RE.findall(raw))
    rev_ids = set(PROJECT_ID_RE.findall(reverse))
    missing = raw_ids - rev_ids
    if missing:
        failures.append(f"check 1 실패: 다음 식별자 누락 — {', '.join(sorted(missing))}")

    # check 2: canonical 표기 (대문자 underscore 강제)
    lower_ids = re.findall(
        r'\b(?:tbl|proc|func|pkg|seq|fk|pk)_\w+\b',
        reverse,
        re.IGNORECASE,
    )
    bad_case = [x for x in lower_ids if x != x.upper()]
    if bad_case:
        failures.append(f"check 2 실패: 소문자 식별자 발견 — {', '.join(bad_case[:5])}")

    # check 3: enum 값 단독 등장 금지 (TBL.COL='val' 형태 강제)
    standalone_enums = STANDALONE_ENUM_RE.findall(reverse)
    if standalone_enums:
        failures.append(
            f"check 3 실패: enum 단독 등장 — {', '.join(standalone_enums[:5])}. "
            "반드시 TBL.COL='val' 형태 사용"
        )

    # check 4: 컬럼명 단독 등장 금지 (점 표기 강제)
    # 프로젝트 prefix가 없고 점 표기도 없는 대문자_언더스코어 패턴 감지
    standalone_cols = STANDALONE_COL_RE.findall(reverse)
    non_prefixed = [
        c for c in standalone_cols
        if not re.match(r'^(?:TBL|PROC|FUNC|PKG|SEQ|FK|PK)_', c)
        and c not in rev_ids  # 이미 프로젝트 식별자로 분류된 것 제외
        and not re.search(rf'\.{re.escape(c)}\b', reverse)  # 점 표기로도 등장하면 OK
    ]
    if non_prefixed:
        failures.append(
            f"check 4 실패: 컬럼명 단독 등장 — {', '.join(non_prefixed[:5])}. "
            "반드시 TBL_NAME.COLUMN_NAME 형태 사용"
        )

    if not failures:
        return ValidationResult(passed=True)
    return ValidationResult(passed=False, feedback="\n".join(failures))
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_validator.py -v`
Expected: 모든 테스트 pass (일부 check 4 휴리스틱은 false positive 가능성 있으므로 실패 시 테스트 케이스 조정)

- [ ] **Step 5: 커밋**

```bash
git add validator.py tests/test_validator.py
git commit -m "feat: validator check 1-4"
```

---

### Task 6: llm_client.py

**Files:**
- Create: `llm_client.py`
- Create: `tests/test_llm_client.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_llm_client.py
import asyncio
import pytest
import httpx
from unittest.mock import AsyncMock, patch
from config import Config
from llm_client import LLMClient


@pytest.fixture
def config():
    return Config(
        llm_url="http://test-llm/v1/chat/completions",
        llm_model="test-model",
        llm_api_key="test-key",
        llm_timeout=10,
        llm_concurrency=2,
    )


@pytest.mark.asyncio
async def test_generate_success(config):
    mock_response = {
        "choices": [{"message": {"content": "생성된 역문서 내용"}}]
    }
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=mock_response)
    )
    async with LLMClient(config, transport=transport) as client:
        result = await client.generate(system="시스템 프롬프트", user="소스 코드")
    assert result == "생성된 역문서 내용"


@pytest.mark.asyncio
async def test_generate_strips_whitespace(config):
    mock_response = {
        "choices": [{"message": {"content": "  역문서\n  "}}]
    }
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=mock_response)
    )
    async with LLMClient(config, transport=transport) as client:
        result = await client.generate(system="sys", user="user")
    assert result == "역문서"


@pytest.mark.asyncio
async def test_generate_server_error_raises(config):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(500, text="Internal Server Error")
    )
    async with LLMClient(config, transport=transport) as client:
        with pytest.raises(Exception):
            await client.generate(system="sys", user="user")


@pytest.mark.asyncio
async def test_semaphore_limits_concurrency(config):
    """LLM_CONCURRENCY=2 이면 동시에 최대 2개만 실행."""
    active = 0
    max_active = 0

    async def slow_handler(request):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        active -= 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    transport = httpx.MockTransport(slow_handler)
    async with LLMClient(config, transport=transport) as client:
        tasks = [client.generate(system="s", user="u") for _ in range(5)]
        await asyncio.gather(*tasks)

    assert max_active <= 2
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_llm_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'llm_client'`

- [ ] **Step 3: llm_client.py 구현**

```python
# llm_client.py
import asyncio
import logging

import httpx

from config import Config

logger = logging.getLogger(__name__)

RETRY_DELAYS = [1, 2]


class LLMClient:
    def __init__(self, config: Config, transport: httpx.AsyncBaseTransport | None = None):
        self.config = config
        self.semaphore = asyncio.Semaphore(config.llm_concurrency)
        headers = {"Content-Type": "application/json"}
        if config.llm_api_key:
            headers["Authorization"] = f"Bearer {config.llm_api_key}"
        self._client = httpx.AsyncClient(
            timeout=config.llm_timeout,
            headers=headers,
            transport=transport,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    async def close(self):
        await self._client.aclose()

    async def generate(self, system: str, user: str, model: str | None = None) -> str:
        payload = {
            "model": model or self.config.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        async with self.semaphore:
            for attempt in range(3):
                try:
                    resp = await self._client.post(self.config.llm_url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    logger.warning("LLM attempt %d failed (transient): %s", attempt + 1, e)
                    if attempt < 2:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                    else:
                        raise
                except httpx.HTTPStatusError as e:
                    if e.response.status_code >= 500 and attempt < 2:
                        logger.warning("LLM attempt %d server error %d", attempt + 1, e.response.status_code)
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                    else:
                        raise
        raise RuntimeError("LLM generate exhausted retries")
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_llm_client.py -v`
Expected: 4 passed

- [ ] **Step 5: 커밋**

```bash
git add llm_client.py tests/test_llm_client.py
git commit -m "feat: llm_client (OpenAI-compatible, Semaphore, retry)"
```

---

### Task 7: rag_client.py

**Files:**
- Create: `rag_client.py`
- Create: `tests/test_rag_client.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_rag_client.py
import pytest
import httpx
from config import Config
from rag_client import RAGClient


@pytest.fixture
def config():
    return Config(
        lightrag_url="http://test-rag",
        lightrag_api_key="test-key",
        rag_timeout=5,
    )


@pytest.mark.asyncio
async def test_query_success(config):
    mock_response = {"response": "TBL_LOAN_APPLICATION은 대출 신청 테이블..."}
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=mock_response)
    )
    async with RAGClient(config, transport=transport) as client:
        result = await client.query("PKG_AUTO_LOAN_APPROVAL TBL_LOAN_APPLICATION")
    assert "TBL_LOAN_APPLICATION" in result


@pytest.mark.asyncio
async def test_query_connection_error_returns_empty(config):
    def raise_error(request):
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(raise_error)
    async with RAGClient(config, transport=transport) as client:
        result = await client.query("PKG_TEST")
    assert result == ""


@pytest.mark.asyncio
async def test_query_timeout_returns_empty(config):
    def raise_timeout(request):
        raise httpx.TimeoutException("timeout")

    transport = httpx.MockTransport(raise_timeout)
    async with RAGClient(config, transport=transport) as client:
        result = await client.query("PKG_TEST")
    assert result == ""


@pytest.mark.asyncio
async def test_query_empty_kb_returns_empty(config):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"response": ""})
    )
    async with RAGClient(config, transport=transport) as client:
        result = await client.query("PKG_TEST")
    assert result == ""
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_rag_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rag_client'`

- [ ] **Step 3: rag_client.py 구현**

```python
# rag_client.py
import logging

import httpx

from config import Config

logger = logging.getLogger(__name__)


class RAGClient:
    def __init__(self, config: Config, transport: httpx.AsyncBaseTransport | None = None):
        self.config = config
        headers = {}
        if config.lightrag_api_key:
            headers["Authorization"] = f"Bearer {config.lightrag_api_key}"
        self._client = httpx.AsyncClient(
            timeout=config.rag_timeout,
            headers=headers,
            transport=transport,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    async def close(self):
        await self._client.aclose()

    async def query(self, query: str, mode: str = "mix") -> str:
        """LightRAG REST API 쿼리. 실패 또는 빈 응답 시 "" 반환 + WARN 로깅."""
        try:
            resp = await self._client.post(
                f"{self.config.lightrag_url}/query",
                json={"query": query, "mode": mode},
            )
            resp.raise_for_status()
            data = resp.json()
            context = data.get("response", "").strip()
            if not context:
                logger.warning("RAG query returned empty context for: %s", query[:100])
            return context
        except httpx.TimeoutException:
            logger.warning("RAG query timeout for: %s", query[:100])
            return ""
        except httpx.ConnectError:
            logger.warning("RAG service unreachable: %s", self.config.lightrag_url)
            return ""
        except Exception as e:
            logger.warning("RAG query failed: %s", e)
            return ""
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_rag_client.py -v`
Expected: 4 passed

- [ ] **Step 5: 커밋**

```bash
git add rag_client.py tests/test_rag_client.py
git commit -m "feat: rag_client (query-only, graceful fallback)"
```

---

### Task 8: prompts.py

**Files:**
- Create: `prompts.py`

- [ ] **Step 1: prompts.py 작성**

```python
# prompts.py
"""PromptStore 초기 시드 콘텐츠. asset_type별 v2 표준 역문서 생성 프롬프트."""

PLSQL_PROMPT = """당신은 Oracle PL/SQL 전문가이자 역문서 생성기다.
아래 PL/SQL 패키지 소스 코드와 참조 컨텍스트를 읽고, v2 표준에 따라 역문서 Markdown을 생성하라.

## v2 표준 표기 규칙 (반드시 준수)

1. **식별자를 문법적 주체/객체 자리에 박는다** — PROC_*, TBL_*, FUNC_*, PKG_* 등을 한국어 조사 앞에 직접 배치.
   올바름: "PROC_CREDIT_EVALUATION은 TBL_LOAN_APPLICATION.STATUS를 변경한다."
   금지: "신용평가 프로시저(PROC_CREDIT_EVALUATION)가..."

2. **컬럼은 반드시 점 표기** — TBL_NAME.COLUMN_NAME 형태.
   금지: EVAL_TYPE 단독 등장.

3. **enum 값은 TBL.COL='val' 형태 강제** — 단독 'REJECTED' 금지.
   올바름: TBL_LOAN_APPLICATION.STATUS = 'APPROVED'
   금지: 'APPROVED' 단독 등장.

4. **거절 사유 코드는 unquoted 단독 허용** — CREDIT_LOW, LTV_EXCEEDED 등.

5. **업무 정책 canonical 명 사용** — "대출 한도 산정 정책", "신용평가 정책" 등 정확히.
   금지: "신용평가 기준", "한도 정책" 등 동의어.

## 출력 형식

패키지 설명 한 단락 후, PROC/FUNC 단위로 ## 헤더 절을 구성한다.
각 절은 해당 프로시저/함수의 역할, 처리 흐름, 테이블/컬럼 조작, 거절 분기를 담는다.

예시:
## PROC_CREDIT_EVALUATION

PROC_CREDIT_EVALUATION은 신용평가 정책에 따라 신청 건의 신용 적격성을 판정한다. ...
"""

DICTIONARY_PROMPT = """당신은 Oracle 데이터 딕셔너리 전문가이자 역문서 생성기다.
아래 테이블/컬럼 정의를 읽고, v2 표준에 따라 역문서 Markdown을 생성하라.

## v2 표준 표기 규칙

1. 테이블은 TBL_* 그대로, 컬럼은 TBL_NAME.COLUMN_NAME 점 표기.
2. PK는 PK_*, FK는 FK_* 그대로.
3. SEQ_*는 SEQ_* 그대로.

## 출력 형식

TBL 단위로 ## 헤더 절. 각 절에 테이블 역할, 컬럼 목록(점 표기), PK/FK/SEQ 관계 기술.
"""

ERD_PROMPT = """당신은 Oracle ERD 전문가이자 역문서 생성기다.
아래 테이블 간 관계를 읽고, v2 표준에 따라 역문서 Markdown을 생성하라.

## v2 표준 표기 규칙

테이블 관계는 "TBL_X.컬럼 → TBL_Y.컬럼 (1:N)" 형태로 자연어 설명.
FK는 FK_* 그대로.

## 출력 형식

TBL 간 관계 단위로 ## 헤더 절.
"""

POLICY_PROMPT = """당신은 업무 정책 문서 전문가이자 역문서 생성기다.
아래 업무 정책 문서를 읽고, v2 표준에 따라 역문서 Markdown을 생성하라.

## v2 표준 표기 규칙

정책 canonical 명을 첫 문장에 주어로 배치. 동의어 금지.
관련 테이블/컬럼/프로시저가 언급되면 반드시 canonical 식별자(점 표기)로.

## 출력 형식

정책 단위로 ## 헤더 절. 정책명, 적용 조건, 관련 식별자, 예외 사항 포함.
"""

ASSET_PROMPTS: dict[str, str] = {
    "plsql": PLSQL_PROMPT,
    "dictionary": DICTIONARY_PROMPT,
    "erd": ERD_PROMPT,
    "policy": POLICY_PROMPT,
}


async def seed_prompts(prompt_store) -> None:
    """PromptStore에 초기 프롬프트 시드. 이미 있으면 skip."""
    for asset_type, text in ASSET_PROMPTS.items():
        await prompt_store.seed_if_empty(asset_type, text)
```

- [ ] **Step 2: 커밋**

```bash
git add prompts.py
git commit -m "feat: prompts (v2 standard seed prompts per asset_type)"
```

---

### Task 9: callback.py

**Files:**
- Create: `callback.py`
- Create: `tests/test_callback.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_callback.py
import pytest
import httpx
from callback import send_callback

CALLBACK_URL = "http://ingestion-router/callback/forge"


@pytest.mark.asyncio
async def test_send_callback_success():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"ok": True})
    )
    # 성공 시 예외 없음
    await send_callback(
        url=CALLBACK_URL,
        payload={"forge_job_id": "abc", "content": "# 역문서", "forge_status": "completed"},
        transport=transport,
    )


@pytest.mark.asyncio
async def test_send_callback_no_url_skips():
    # callback_url이 None이면 아무것도 안 함 (예외 없음)
    await send_callback(url=None, payload={"forge_job_id": "x"})


@pytest.mark.asyncio
async def test_send_callback_retry_on_failure():
    call_count = 0

    def flaky_handler(request):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(500, text="error")
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(flaky_handler)
    await send_callback(
        url=CALLBACK_URL,
        payload={"forge_job_id": "abc", "content": "ok", "forge_status": "completed"},
        transport=transport,
    )
    assert call_count == 3


@pytest.mark.asyncio
async def test_send_callback_all_retries_fail_no_raise():
    # 3회 모두 실패해도 예외를 올리지 않음 (로그만)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(500, text="always fails")
    )
    await send_callback(
        url=CALLBACK_URL,
        payload={"forge_job_id": "abc", "content": "x", "forge_status": "failed"},
        transport=transport,
    )
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_callback.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'callback'`

- [ ] **Step 3: callback.py 구현**

```python
# callback.py
import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

RETRIES = 3
DELAYS = [1, 2, 4]


async def send_callback(
    url: str | None,
    payload: dict,
    api_key: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """ingestion-router로 완료 콜백 전송. 실패 시 3회 retry, 최종 실패는 로그만."""
    if not url:
        return

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    client_kwargs: dict = {"timeout": 30, "headers": headers}
    if transport:
        client_kwargs["transport"] = transport

    async with httpx.AsyncClient(**client_kwargs) as client:
        for attempt in range(RETRIES):
            try:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                logger.info("Callback sent to %s (status %d)", url, resp.status_code)
                return
            except Exception as e:
                logger.warning("Callback attempt %d/%d failed: %s", attempt + 1, RETRIES, e)
                if attempt < RETRIES - 1:
                    await asyncio.sleep(DELAYS[attempt])
    logger.error("Callback failed after %d attempts: %s", RETRIES, url)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_callback.py -v`
Expected: 4 passed

- [ ] **Step 5: 커밋**

```bash
git add callback.py tests/test_callback.py
git commit -m "feat: callback (3-retry, graceful failure)"
```

---

### Task 10: processor.py

**Files:**
- Create: `processor.py`
- Create: `tests/test_processor.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_processor.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from processor import to_reverse_doc, extract_hint_keywords
from job_store import InMemoryJobStore, InMemoryPromptStore
from models import JobStatus


# --- extract_hint_keywords ---

def test_extract_hint_keywords_basic():
    source = "PROCEDURE PROC_CREDIT_EVALUATION IS BEGIN SELECT * FROM TBL_LOAN_APPLICATION; END;"
    hints = extract_hint_keywords(source)
    assert "PROC_CREDIT_EVALUATION" in hints
    assert "TBL_LOAN_APPLICATION" in hints


def test_extract_hint_keywords_excludes_sql_keywords():
    source = "BEGIN END IF EXCEPTION VARCHAR2 NUMBER NULL"
    hints = extract_hint_keywords(source)
    assert hints == ""  # SQL 키워드는 hint에 포함되지 않음


def test_extract_hint_keywords_deduplicates():
    source = "TBL_LOAN_APPLICATION.STATUS TBL_LOAN_APPLICATION.AMOUNT"
    hints = extract_hint_keywords(source)
    # TBL_LOAN_APPLICATION이 중복 없이 한 번만
    assert hints.count("TBL_LOAN_APPLICATION") == 1


# --- to_reverse_doc pipeline ---

@pytest.fixture
def store():
    return InMemoryJobStore()


@pytest.fixture
def prompt_store():
    ps = InMemoryPromptStore()
    return ps


@pytest.mark.asyncio
async def test_to_reverse_doc_success(store, prompt_store):
    """정상 경로: RAG context 조회 → LLM 생성 → validate 통과 → job completed."""
    await prompt_store.seed_if_empty("plsql", "시스템 프롬프트")
    job = await store.create(
        asset_type="plsql",
        file_name="PKG_TEST.sql",
        source_hash="h1",
        callback_url=None,
    )

    llm = AsyncMock()
    llm.generate = AsyncMock(return_value=(
        "## PROC_TEST\nPROC_TEST는 TBL_TEST를 조회한다. "
        "TBL_TEST.STATUS = 'ACTIVE'로 확인한다."
    ))

    rag = AsyncMock()
    rag.query = AsyncMock(return_value="TBL_TEST: 테스트 테이블")

    await to_reverse_doc(
        raw=b"PROCEDURE PROC_TEST IS BEGIN SELECT * FROM TBL_TEST; END;",
        asset_type="plsql",
        job_id=job.id,
        callback_url=None,
        store=store,
        llm=llm,
        rag=rag,
        prompt_store=prompt_store,
    )

    updated = await store.get(job.id)
    assert updated.status == JobStatus.COMPLETED
    assert updated.result is not None
    assert "PROC_TEST" in updated.result


@pytest.mark.asyncio
async def test_to_reverse_doc_retry_on_validation_failure(store, prompt_store):
    """validate 실패 후 재시도 성공 경로."""
    await prompt_store.seed_if_empty("plsql", "프롬프트")
    job = await store.create(
        asset_type="plsql", file_name="f.sql", source_hash="h2", callback_url=None
    )

    call_count = 0

    async def mock_generate(system, user, model=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # 첫 번째: validate 실패할 내용 (PROC_MISSING 누락)
            return "역문서 내용 (식별자 누락)"
        # 두 번째: 올바른 내용
        return "PROC_MISSING은 TBL_DATA.STATUS = 'OK'로 처리한다."

    llm = AsyncMock()
    llm.generate = mock_generate
    rag = AsyncMock()
    rag.query = AsyncMock(return_value="")

    await to_reverse_doc(
        raw=b"PROCEDURE PROC_MISSING IS BEGIN SELECT STATUS FROM TBL_DATA; END;",
        asset_type="plsql",
        job_id=job.id,
        callback_url=None,
        store=store,
        llm=llm,
        rag=rag,
        prompt_store=prompt_store,
    )

    updated = await store.get(job.id)
    assert updated.status == JobStatus.COMPLETED
    assert call_count == 2


@pytest.mark.asyncio
async def test_to_reverse_doc_all_retries_fail(store, prompt_store):
    """3회 모두 validate 실패 → job FAILED."""
    await prompt_store.seed_if_empty("plsql", "프롬프트")
    job = await store.create(
        asset_type="plsql", file_name="f.sql", source_hash="h3", callback_url=None
    )

    llm = AsyncMock()
    llm.generate = AsyncMock(return_value="validate 항상 실패할 내용")
    rag = AsyncMock()
    rag.query = AsyncMock(return_value="")

    await to_reverse_doc(
        raw=b"PROCEDURE PROC_IMPORTANT IS BEGIN NULL; END;",
        asset_type="plsql",
        job_id=job.id,
        callback_url=None,
        store=store,
        llm=llm,
        rag=rag,
        prompt_store=prompt_store,
    )

    updated = await store.get(job.id)
    assert updated.status == JobStatus.FAILED
    assert "검증 실패" in updated.error


@pytest.mark.asyncio
async def test_to_reverse_doc_empty_rag_context(store, prompt_store):
    """RAG 실패 → empty context + WARN 후 LLM 정상 호출."""
    await prompt_store.seed_if_empty("plsql", "프롬프트")
    job = await store.create(
        asset_type="plsql", file_name="f.sql", source_hash="h4", callback_url=None
    )

    llm = AsyncMock()
    llm.generate = AsyncMock(
        return_value="PROC_EMPTY는 TBL_EMPTY.STATUS = 'DONE'으로 처리한다."
    )
    rag = AsyncMock()
    rag.query = AsyncMock(return_value="")  # empty context

    await to_reverse_doc(
        raw=b"PROCEDURE PROC_EMPTY IS BEGIN UPDATE TBL_EMPTY SET STATUS='DONE'; END;",
        asset_type="plsql",
        job_id=job.id,
        callback_url=None,
        store=store,
        llm=llm,
        rag=rag,
        prompt_store=prompt_store,
    )

    updated = await store.get(job.id)
    assert updated.status == JobStatus.COMPLETED
    llm.generate.assert_called_once()  # LLM은 한 번 호출됨
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_processor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'processor'`

- [ ] **Step 3: processor.py 구현**

```python
# processor.py
import hashlib
import logging
import re

from callback import send_callback
from job_store import JobStore
from llm_client import LLMClient
from models import JobStatus
from rag_client import RAGClient
from validator import validate

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
PROJECT_ID_RE = re.compile(r'\b(?:TBL|PROC|FUNC|PKG|SEQ|FK|PK)_[A-Z0-9_]+\b')


def extract_hint_keywords(source: str | bytes) -> str:
    """소스에서 project 식별자만 추출해 RAG 쿼리 힌트 생성."""
    if isinstance(source, bytes):
        source = source.decode("utf-8", errors="replace")
    ids = sorted(set(PROJECT_ID_RE.findall(source)))
    return " ".join(ids)


def compute_source_hash(source: bytes, prompt_version: str) -> str:
    return hashlib.sha256(source + prompt_version.encode()).hexdigest()


async def to_reverse_doc(
    raw: bytes,
    asset_type: str,
    job_id: str,
    callback_url: str | None,
    store: JobStore,
    llm: LLMClient,
    rag: RAGClient,
    prompt_store,
) -> None:
    """역문서화 파이프라인. 결과를 store에 저장하고 callback 전송."""
    await store.update_status(job_id, JobStatus.PROCESSING)

    try:
        # 1. 프롬프트 조회
        prompt_info = await prompt_store.get_active(asset_type)
        if prompt_info is None:
            raise ValueError(f"No active prompt for asset_type: {asset_type}")
        system_prompt = prompt_info["text"]

        # 2. RAG context 조회
        hint = extract_hint_keywords(raw)
        context = await rag.query(hint) if hint else ""
        if not context:
            logger.warning("Empty RAG context for job %s (asset_type=%s)", job_id, asset_type)

        # 3. LLM 생성 + 검증 (최대 MAX_RETRIES회)
        source_text = raw.decode("utf-8", errors="replace")
        user_content = f"[원문]\n{source_text}\n\n[참조 컨텍스트]\n{context}"
        result = None
        last_feedback = None

        for attempt in range(MAX_RETRIES):
            await store.increment_attempts(job_id)

            prompt_with_feedback = system_prompt
            if last_feedback:
                prompt_with_feedback += f"\n\n## 재시도 피드백\n{last_feedback}"

            result = await llm.generate(system=prompt_with_feedback, user=user_content)

            verdict = validate(raw=source_text, reverse=result)
            if verdict.passed:
                break
            last_feedback = verdict.feedback
            logger.warning(
                "Job %s attempt %d validation failed: %s",
                job_id, attempt + 1, verdict.feedback,
            )
        else:
            # 3회 모두 실패
            await store.save_error(job_id, f"검증 실패 (3회): {last_feedback}")
            await send_callback(
                url=callback_url,
                payload={"forge_job_id": job_id, "content": "", "forge_status": "failed", "forge_error": last_feedback},
            )
            return

        # 4. 결과 저장
        await store.save_result(job_id, result)

        # 5. Callback 전송
        await send_callback(
            url=callback_url,
            payload={"forge_job_id": job_id, "content": result, "forge_status": "completed", "forge_error": None},
        )

    except Exception as e:
        logger.exception("Unexpected error in job %s", job_id)
        await store.save_error(job_id, str(e))
        await send_callback(
            url=callback_url,
            payload={"forge_job_id": job_id, "content": "", "forge_status": "failed", "forge_error": str(e)},
        )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_processor.py -v`
Expected: 5 passed

- [ ] **Step 5: 커밋**

```bash
git add processor.py tests/test_processor.py
git commit -m "feat: processor (RAG→LLM→validate→callback pipeline)"
```

---

### Task 11: worker.py

**Files:**
- Create: `worker.py`

- [ ] **Step 1: worker.py 구현**

```python
# worker.py
import asyncio
import logging
import os

from config import Config
from job_store import JobStore
from llm_client import LLMClient
from models import Job
from processor import to_reverse_doc
from rag_client import RAGClient

logger = logging.getLogger(__name__)


async def _safe_process(
    job: Job,
    raw: bytes,
    store: JobStore,
    config: Config,
    llm: LLMClient,
    rag: RAGClient,
    prompt_store,
) -> None:
    """asyncio.create_task용 래퍼. 미처리 예외를 로깅."""
    try:
        await to_reverse_doc(
            raw=raw,
            asset_type=job.asset_type,
            job_id=job.id,
            callback_url=job.callback_url,
            store=store,
            llm=llm,
            rag=rag,
            prompt_store=prompt_store,
        )
    except Exception:
        logger.exception("Unhandled error in job %s", job.id)
```

- [ ] **Step 2: 커밋**

```bash
git add worker.py
git commit -m "feat: worker (_safe_process wrapper)"
```

---

### Task 12: app.py

**Files:**
- Create: `app.py`
- Create: `tests/test_app.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_app.py
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from app import create_app
from job_store import InMemoryJobStore, InMemoryPromptStore
from config import Config
from models import Job, JobStatus


@pytest.fixture
def app_client():
    config = Config(llm_url="http://mock-llm", lightrag_url="http://mock-rag")
    store = InMemoryJobStore()
    prompt_store = InMemoryPromptStore()

    app = create_app(store=store, config=config, prompt_store=prompt_store)
    return httpx.AsyncClient(app=app, base_url="http://test"), store, prompt_store


@pytest.mark.asyncio
async def test_health(app_client):
    client, store, ps = app_client
    async with client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_post_jobs_returns_job_id(app_client):
    client, store, ps = app_client
    await ps.seed_if_empty("plsql", "테스트 프롬프트")

    content = b"PROCEDURE PROC_TEST IS BEGIN NULL; END;"

    with patch("app._safe_process", new_callable=AsyncMock):
        async with client:
            resp = await client.post(
                "/jobs",
                data={"asset_type": "plsql"},
                files={"file": ("test.sql", content, "text/plain")},
            )

    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_post_jobs_dedup_same_hash(app_client):
    """동일 소스 + 동일 프롬프트 → 기존 job_id 반환."""
    client, store, ps = app_client
    await ps.seed_if_empty("plsql", "프롬프트 v1")

    content = b"PROCEDURE PROC_SAME IS BEGIN NULL; END;"

    with patch("app._safe_process", new_callable=AsyncMock):
        async with client:
            resp1 = await client.post(
                "/jobs",
                data={"asset_type": "plsql"},
                files={"file": ("f.sql", content, "text/plain")},
            )
            resp2 = await client.post(
                "/jobs",
                data={"asset_type": "plsql"},
                files={"file": ("f.sql", content, "text/plain")},
            )

    assert resp1.json()["job_id"] == resp2.json()["job_id"]


@pytest.mark.asyncio
async def test_get_job_not_found(app_client):
    client, store, ps = app_client
    async with client:
        resp = await client.get("/jobs/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_job_result_not_ready(app_client):
    client, store, ps = app_client
    await ps.seed_if_empty("plsql", "프롬프트")
    job = await store.create(asset_type="plsql", file_name="f.sql", source_hash="h_test")

    async with client:
        resp = await client.get(f"/jobs/{job.id}/result")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_job_result_completed(app_client):
    client, store, ps = app_client
    job = await store.create(asset_type="plsql", file_name="f.sql", source_hash="h_done")
    await store.save_result(job.id, "# PROC_DONE\nPROC_DONE은 완료됐다.")

    async with client:
        resp = await client.get(f"/jobs/{job.id}/result")
    assert resp.status_code == 200
    assert "PROC_DONE" in resp.json()["result"]


@pytest.mark.asyncio
async def test_file_too_large(app_client):
    client, store, ps = app_client
    await ps.seed_if_empty("plsql", "프롬프트")

    large_content = b"X" * (201 * 1024)  # 201KB > 200KB 제한

    async with client:
        resp = await client.post(
            "/jobs",
            data={"asset_type": "plsql"},
            files={"file": ("big.sql", large_content, "text/plain")},
        )
    assert resp.status_code == 413
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: app.py 구현**

```python
# app.py
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile

from auth import verify_api_key
from config import Config
from job_store import InMemoryJobStore, InMemoryPromptStore, JobStore
from models import JobStatus
from processor import compute_source_hash
from prompts import seed_prompts
from worker import _safe_process

logger = logging.getLogger(__name__)

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


async def _apply_schema(pool) -> None:
    if not os.path.isfile(SCHEMA_PATH):
        logger.warning("schema.sql not found, skipping")
        return
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        ddl = f.read()
    async with pool.acquire() as conn:
        await conn.execute(ddl)
    logger.info("schema.sql applied")


def create_app(
    store: JobStore | None = None,
    config: Config | None = None,
    prompt_store=None,
) -> FastAPI:
    config = config or Config()
    store = store or InMemoryJobStore()
    prompt_store = prompt_store or InMemoryPromptStore()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = store
        app.state.config = config
        app.state.prompt_store = prompt_store

        if config.database_url:
            import asyncpg
            from job_store import PostgresJobStore, PromptStore
            from llm_client import LLMClient
            from rag_client import RAGClient

            pool = await asyncpg.create_pool(config.database_url)
            app.state.pool = pool
            await _apply_schema(pool)
            app.state.store = PostgresJobStore(pool)
            app.state.prompt_store = PromptStore(pool)

            app.state.llm = LLMClient(config)
            app.state.rag = RAGClient(config)
        else:
            from unittest.mock import AsyncMock
            app.state.llm = AsyncMock()
            app.state.rag = AsyncMock()

        await seed_prompts(app.state.prompt_store)

        yield

        if hasattr(app.state, "llm") and hasattr(app.state.llm, "close"):
            await app.state.llm.close()
        if hasattr(app.state, "rag") and hasattr(app.state.rag, "close"):
            await app.state.rag.close()
        if hasattr(app.state, "pool"):
            await app.state.pool.close()

    app = FastAPI(title="Reverse-Doc Service", version="1.0.0", lifespan=lifespan)

    from admin import create_admin_router
    auth_dep = verify_api_key(config)
    admin_router = create_admin_router(lambda: app.state, auth_dep)
    app.include_router(admin_router, prefix="/admin")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/jobs", status_code=202)
    async def create_job(
        request: Request,
        file: UploadFile = File(...),
        asset_type: str = Form(...),
        callback_url: str | None = Form(None),
        requested_by: str | None = Form(None),
    ):
        raw = await file.read()
        if len(raw) > config.max_file_size_kb * 1024:
            raise HTTPException(status_code=413, detail=f"File exceeds {config.max_file_size_kb}KB limit")

        current_store = request.app.state.store
        current_prompt_store = request.app.state.prompt_store

        prompt_info = await current_prompt_store.get_active(asset_type)
        if prompt_info is None:
            raise HTTPException(status_code=400, detail=f"Unsupported asset_type: {asset_type}")

        prompt_version = str(prompt_info.get("version", "1"))
        source_hash = compute_source_hash(raw, prompt_version)

        existing = await current_store.get_by_hash(source_hash)
        if existing:
            return {"job_id": existing.id, "status": existing.status, "cached": True}

        job = await current_store.create(
            asset_type=asset_type,
            file_name=file.filename or "unknown",
            source_hash=source_hash,
            file_size=len(raw),
            callback_url=callback_url,
            requested_by=requested_by,
        )
        job.callback_url = callback_url

        asyncio.create_task(
            _safe_process(
                job=job,
                raw=raw,
                store=current_store,
                config=config,
                llm=request.app.state.llm,
                rag=request.app.state.rag,
                prompt_store=current_prompt_store,
            )
        )

        return {"job_id": job.id, "status": job.status}

    @app.get("/jobs/{job_id}")
    async def get_job(job_id: str, request: Request):
        job = await request.app.state.store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return {
            "job_id": job.id,
            "status": job.status,
            "asset_type": job.asset_type,
            "file_name": job.file_name,
            "attempts": job.attempts,
            "error": job.error,
            "created_at": str(job.created_at),
            "started_at": str(job.started_at) if job.started_at else None,
            "completed_at": str(job.completed_at) if job.completed_at else None,
        }

    @app.get("/jobs/{job_id}/result")
    async def get_job_result(job_id: str, request: Request):
        job = await request.app.state.store.get(job_id)
        if job is None or job.status != JobStatus.COMPLETED:
            raise HTTPException(status_code=404, detail="Job not completed or not found")
        return {"job_id": job.id, "status": job.status, "result": job.result}

    @app.delete("/jobs/{job_id}", status_code=204)
    async def delete_job(job_id: str, request: Request):
        job = await request.app.state.store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        # InMemoryJobStore: 단순 삭제. PostgresJobStore: soft delete (deleted_at 설정)
        if hasattr(request.app.state.store, "delete"):
            await request.app.state.store.delete(job_id)

    return app
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_app.py -v`
Expected: 7 passed

- [ ] **Step 5: 커밋**

```bash
git add app.py tests/test_app.py
git commit -m "feat: app (FastAPI + 5 endpoints + lifespan)"
```

---

### Task 13: admin.py

**Files:**
- Create: `admin.py`

- [ ] **Step 1: admin.py 구현**

```python
# admin.py
from fastapi import APIRouter, Depends, HTTPException, Query


def create_admin_router(get_state, auth_dep) -> APIRouter:
    router = APIRouter(dependencies=[Depends(auth_dep)], tags=["관리"])

    @router.get("/jobs", summary="Job 목록")
    async def list_jobs(
        status: str | None = Query(None),
        asset_type: str | None = Query(None),
        page: int = Query(1, ge=1),
        size: int = Query(20, ge=1, le=100),
    ):
        state = get_state()
        store = state.store
        if not hasattr(store, "list_jobs"):
            raise HTTPException(status_code=501, detail="list_jobs not supported")
        jobs, total = await store.list_jobs(
            page=page, size=size, status=status, asset_type=asset_type
        )
        return {"jobs": jobs, "total": total, "page": page, "size": size}

    @router.post("/jobs/{job_id}/retry", summary="Job 강제 재시도")
    async def retry_job(job_id: str):
        import asyncio
        from models import JobStatus
        from worker import _safe_process

        state = get_state()
        store = state.store
        job = await store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status not in (JobStatus.FAILED,):
            raise HTTPException(status_code=400, detail="Only failed jobs can be retried")

        # hash를 변경해 중복 체크를 우회 (강제 재처리)
        import hashlib, time
        new_hash = hashlib.sha256(f"{job.source_hash}-retry-{time.time()}".encode()).hexdigest()
        new_job = await store.create(
            asset_type=job.asset_type,
            file_name=job.file_name,
            source_hash=new_hash,
            callback_url=job.callback_url,
            requested_by=job.requested_by,
        )
        new_job.callback_url = job.callback_url

        # 원본 소스는 유실됐으므로 재시도는 소스 재업로드 필요 — 이 엔드포인트는 job 메타 재생성용
        # 실제 구현에서는 원본 raw를 DB에 저장하거나 S3에서 조회
        return {"job_id": new_job.id, "status": new_job.status, "note": "재시도 job 생성됨. 소스 재업로드 필요."}

    return router
```

- [ ] **Step 2: 커밋**

```bash
git add admin.py
git commit -m "feat: admin (list jobs, retry)"
```

---

### Task 14: Dockerfile + 진입점

**Files:**
- Create: `Dockerfile`
- Create: `main.py`

- [ ] **Step 1: main.py 작성**

```python
# main.py
import logging
import uvicorn
from app import create_app
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

config = Config()
app = create_app(config=config)

if __name__ == "__main__":
    uvicorn.run("main:app", host=config.host, port=config.port, reload=False)
```

- [ ] **Step 2: Dockerfile 작성**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8004

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]
```

- [ ] **Step 3: 커밋**

```bash
git add Dockerfile main.py
git commit -m "feat: Dockerfile + main entrypoint"
```

---

### Task 15: Mock E2E 테스트

**Files:**
- Create: `tests/test_e2e.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_e2e.py
"""
Mock E2E: POST /jobs → worker 비동기 실행 → GET /jobs/{id}/result 전체 흐름.
실제 LLM/LightRAG 없이 httpx.MockTransport + InMemoryJobStore로 검증.
"""
import asyncio
import pytest
import httpx
from unittest.mock import AsyncMock, patch
from app import create_app
from job_store import InMemoryJobStore, InMemoryPromptStore
from config import Config


@pytest.fixture
def e2e_app():
    config = Config(
        llm_url="http://mock-llm",
        lightrag_url="http://mock-rag",
        max_file_size_kb=200,
    )
    store = InMemoryJobStore()
    prompt_store = InMemoryPromptStore()
    app = create_app(store=store, config=config, prompt_store=prompt_store)
    return app, store, prompt_store, config


@pytest.mark.asyncio
async def test_full_flow_success(e2e_app):
    """
    1. POST /jobs → 202 job_id
    2. worker가 비동기로 LLM 호출 → validate → save_result
    3. GET /jobs/{id}/result → 200 result
    """
    app, store, prompt_store, config = e2e_app
    await prompt_store.seed_if_empty("plsql", "v2 표준 프롬프트")

    source = (
        b"CREATE OR REPLACE PROCEDURE PROC_E2E_TEST IS\n"
        b"BEGIN\n"
        b"  UPDATE TBL_E2E_TABLE SET STATUS = 'DONE' WHERE ID = 1;\n"
        b"END;"
    )

    mock_llm_response = (
        "PROC_E2E_TEST는 TBL_E2E_TABLE을 처리한다. "
        "TBL_E2E_TABLE.STATUS = 'DONE'으로 변경한다."
    )

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        # POST /jobs
        with (
            patch("app._safe_process") as mock_sp,
        ):
            mock_sp.side_effect = None  # create_task에 전달될 실제 coroutine 대체

            resp = await client.post(
                "/jobs",
                data={"asset_type": "plsql"},
                files={"file": ("test.sql", source, "text/plain")},
            )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        # processor를 직접 실행해 worker 동작 시뮬레이션
        from processor import to_reverse_doc
        from unittest.mock import AsyncMock as AM

        llm_mock = AM()
        llm_mock.generate = AM(return_value=mock_llm_response)
        rag_mock = AM()
        rag_mock.query = AM(return_value="TBL_E2E_TABLE: E2E 테스트 테이블")

        await to_reverse_doc(
            raw=source,
            asset_type="plsql",
            job_id=job_id,
            callback_url=None,
            store=store,
            llm=llm_mock,
            rag=rag_mock,
            prompt_store=prompt_store,
        )

        # GET /jobs/{id}/result
        resp = await client.get(f"/jobs/{job_id}/result")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert "PROC_E2E_TEST" in data["result"]
        assert "TBL_E2E_TABLE" in data["result"]


@pytest.mark.asyncio
async def test_full_flow_dedup(e2e_app):
    """동일 소스 두 번 POST → 두 번째는 같은 job_id 반환."""
    app, store, prompt_store, config = e2e_app
    await prompt_store.seed_if_empty("plsql", "프롬프트")

    source = b"PROCEDURE PROC_DEDUP IS BEGIN NULL; END;"

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        with patch("app._safe_process"):
            resp1 = await client.post(
                "/jobs",
                data={"asset_type": "plsql"},
                files={"file": ("f.sql", source, "text/plain")},
            )
            resp2 = await client.post(
                "/jobs",
                data={"asset_type": "plsql"},
                files={"file": ("f.sql", source, "text/plain")},
            )

    id1 = resp1.json()["job_id"]
    id2 = resp2.json()["job_id"]
    assert id1 == id2


@pytest.mark.asyncio
async def test_full_flow_file_too_large(e2e_app):
    app, store, prompt_store, config = e2e_app
    await prompt_store.seed_if_empty("plsql", "프롬프트")

    large_source = b"X" * (201 * 1024)

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post(
            "/jobs",
            data={"asset_type": "plsql"},
            files={"file": ("big.sql", large_source, "text/plain")},
        )
    assert resp.status_code == 413
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_e2e.py -v`
Expected: FAIL (의존 모듈 없음)

- [ ] **Step 3: 전체 테스트 suite 실행**

Run: `python -m pytest tests/ -v`
Expected: 모든 테스트 pass

- [ ] **Step 4: pytest.ini 설정**

```ini
# pytest.ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 5: 최종 커밋**

```bash
git add tests/test_e2e.py pytest.ini
git commit -m "feat: mock E2E test (full pipeline)"
```

---

## 구현 후 체크리스트

- [ ] `python -m pytest tests/ -v` — 전체 통과
- [ ] `.env` 파일 생성 (`.env.example` 기반) — Hostinger DB의 `DATABASE_URL` 설정
- [ ] `python main.py` 또는 `uvicorn main:app --port 8004` 로컬 실행 확인
- [ ] `curl http://localhost:8004/health` → `{"status": "ok"}`
- [ ] DB 연결 후 `schema.sql` 자동 적용 확인 (`rdoc_job`, `rdoc_prompt` 테이블 생성)
- [ ] hcs-ingestion-router에 `REVERSE_DOC_URL=http://reverse-doc:8004` 환경변수 추가 (별도 세션)

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | issues_found | 5 findings (4 반영, 1 TODO) |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 8 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**VERDICT: ENG CLEARED — 구현 시작 가능**
