# Group B — Job 관리 강화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 원본 소스를 DB에 저장해 retry를 완전 자동화하고, 운영 통계 API를 추가한다.

**Architecture:** `source_bytes BYTEA` 컬럼을 추가해 `POST /jobs` 시 원본을 저장하고, retry 시 재업로드 없이 즉시 재처리한다. `GET /admin/stats`는 `get_stats()` 메서드로 단일 조회한다. **이 브랜치는 Group D가 master에 merge된 후 master에서 생성한다.** Group D에서 이미 `source_bytes`와 `rag_mode` 컬럼이 추가됐으므로 이 그룹의 스키마 마이그레이션은 `IF NOT EXISTS`로 안전하게 실행된다.

**Tech Stack:** Python 3.11+, FastAPI, asyncpg, pytest-asyncio

---

## File Map

| 파일 | 변경 | 내용 |
|------|------|------|
| `schema.sql` | Modify | `source_bytes BYTEA` 컬럼 추가 (IF NOT EXISTS — Group D가 먼저 추가했을 수 있음) |
| `models.py` | Modify | `Job`에 `source_bytes: bytes | None = None` 추가 |
| `job_store.py` | Modify | `create()` + `_row_to_job()`에 `source_bytes` 반영, `get_stats()` 추가 |
| `app.py` | Modify | `POST /jobs`에서 `source_bytes=raw` 저장, `_state`에 `config` 노출 |
| `admin.py` | Modify | retry 로직 개선, `GET /admin/stats` 추가 |
| `tests/test_job_store.py` | Modify | `source_bytes` 저장/조회, `get_stats()` 테스트 추가 |
| `tests/test_admin.py` | Modify | retry 자동화, stats 테스트 추가 |

---

### Task 1: 브랜치 생성

- [ ] **Step 1: Group D merge 확인 후 브랜치 생성**

```bash
git checkout master && git pull
git checkout -b feature/group-b
```

---

### Task 2: 스키마 + 모델 업데이트

**Files:**
- Modify: `schema.sql`
- Modify: `models.py`

- [ ] **Step 1: schema.sql 확인 및 멱등 마이그레이션 보강**

`schema.sql` 끝의 기존 Group D 마이그레이션 확인:

```sql
ALTER TABLE rdoc_job ADD COLUMN IF NOT EXISTS source_bytes BYTEA;
ALTER TABLE rdoc_job ADD COLUMN IF NOT EXISTS rag_mode TEXT DEFAULT 'mix';
```

두 줄 이미 있으면 변경 불필요. 없으면 추가.

> `IF NOT EXISTS` 덕분에 중복 실행해도 에러 없음.

- [ ] **Step 2: models.py — Job에 source_bytes 필드 추가**

`models.py`의 `Job` 클래스에서 `rag_mode` 필드 위에 추가:

```python
    source_bytes: bytes | None = None
```

최종 `Job` 클래스:

```python
class Job(BaseModel):
    id: str
    status: JobStatus
    asset_type: str
    file_name: str
    file_size: int | None = None
    source_hash: str
    source_bytes: bytes | None = None
    result: str | None = None
    error: str | None = None
    attempts: int = 0
    callback_url: str | None = None
    requested_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    rag_mode: str = "mix"
```

---

### Task 3: job_store.py — source_bytes + get_stats() (TDD)

**Files:**
- Modify: `job_store.py`
- Modify: `tests/test_job_store.py`

- [ ] **Step 1: tests/test_job_store.py에 source_bytes 테스트 추가**

`tests/test_job_store.py` 끝에 추가:

```python
async def test_create_with_source_bytes(store):
    raw = b"PROCEDURE PROC_TEST IS BEGIN NULL; END;"
    job = await store.create(
        asset_type="plsql",
        file_name="t.sql",
        source_hash="h-bytes",
        source_bytes=raw,
    )
    fetched = await store.get(job.id)
    assert fetched.source_bytes == raw


async def test_create_without_source_bytes(store):
    job = await store.create(asset_type="plsql", file_name="t.sql", source_hash="h-no-bytes")
    fetched = await store.get(job.id)
    assert fetched.source_bytes is None
```

- [ ] **Step 2: 테스트 실행 — 통과 확인 (InMemoryJobStore는 이미 **kwargs 사용)**

```bash
python -m pytest tests/test_job_store.py::test_create_with_source_bytes tests/test_job_store.py::test_create_without_source_bytes -v
```

Expected: PASSED (InMemoryJobStore는 `**kwargs`로 `source_bytes`를 그대로 `Job`에 전달)

- [ ] **Step 3: PostgresJobStore.create() 업데이트 — source_bytes 포함**

기존 (Group D에서 이미 rag_mode 추가한 버전):

```python
    async def create(self, asset_type: str, file_name: str, source_hash: str, **kwargs) -> Job:
        job_id = str(uuid.uuid4())
        row = await self._pool.fetchrow(
            """INSERT INTO rdoc_job
               (job_id, asset_type, file_name, file_size, source_hash,
                callback_url, requested_by, rag_mode)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               RETURNING *""",
            job_id, asset_type, file_name,
            kwargs.get("file_size"), source_hash,
            kwargs.get("callback_url"), kwargs.get("requested_by"),
            kwargs.get("rag_mode", "mix"),
        )
        return self._row_to_job(dict(row))
```

교체:

```python
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
```

- [ ] **Step 4: PostgresJobStore._row_to_job()에 source_bytes 추가**

기존 `_row_to_job`에 `source_bytes` 필드 추가:

```python
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
```

- [ ] **Step 5: tests/test_job_store.py에 get_stats() 테스트 추가**

`tests/test_job_store.py` 끝에 추가:

```python
async def test_get_stats_empty(store):
    stats = await store.get_stats()
    assert stats["total"] == 0
    assert stats["success_rate"] == 0.0
    assert stats["retry_rate"] == 0.0
    assert stats["avg_processing_sec"] is None
    assert stats["recent_failures"] == []


async def test_get_stats_with_jobs(store):
    from datetime import datetime, timezone, timedelta

    # completed job 2개
    j1 = await store.create(asset_type="plsql", file_name="a.sql", source_hash="h1")
    j2 = await store.create(asset_type="plsql", file_name="b.sql", source_hash="h2")
    await store.update_status(j1.id, JobStatus.PROCESSING)
    await store.update_status(j2.id, JobStatus.PROCESSING)
    await store.save_result(j1.id, "# result1")
    await store.save_result(j2.id, "# result2")

    # failed job 1개
    j3 = await store.create(asset_type="dictionary", file_name="c.sql", source_hash="h3")
    await store.save_error(j3.id, "검증 실패")

    # retry job (attempts > 1)
    j4 = await store.create(asset_type="plsql", file_name="d.sql", source_hash="h4")
    await store.increment_attempts(j4.id)
    await store.increment_attempts(j4.id)

    stats = await store.get_stats()
    assert stats["total"] == 4
    assert stats["by_status"]["completed"] == 2
    assert stats["by_status"]["failed"] == 1
    assert stats["by_asset_type"]["plsql"] == 3
    assert stats["by_asset_type"]["dictionary"] == 1
    assert stats["success_rate"] == 50.0
    assert stats["retry_rate"] == 25.0
    assert len(stats["recent_failures"]) == 1
    assert stats["recent_failures"][0]["file_name"] == "c.sql"


async def test_get_stats_avg_processing_sec_null_safe(store):
    """started_at=None인 job이 있어도 avg_processing_sec 계산 시 에러 없음."""
    j1 = await store.create(asset_type="plsql", file_name="a.sql", source_hash="h1")
    # queued 상태 유지 (started_at=None)
    stats = await store.get_stats()
    assert stats["avg_processing_sec"] is None  # completed job 없으므로 None
```

- [ ] **Step 6: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_job_store.py::test_get_stats_empty tests/test_job_store.py::test_get_stats_with_jobs tests/test_job_store.py::test_get_stats_avg_processing_sec_null_safe -v
```

Expected: FAIL — `AttributeError: 'InMemoryJobStore' object has no attribute 'get_stats'`

- [ ] **Step 7: job_store.py — JobStore ABC에 get_stats() 추가**

`JobStore`의 `count_by_status` 추상 메서드 아래에 추가:

```python
    @abstractmethod
    async def get_stats(self) -> dict: ...
```

- [ ] **Step 8: job_store.py — InMemoryJobStore.get_stats() 구현**

`InMemoryJobStore`의 `count_by_status` 메서드 아래에 추가:

```python
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
```

- [ ] **Step 9: job_store.py — PostgresJobStore.get_stats() 구현**

`PostgresJobStore`의 `count_by_status` 메서드 아래에 추가:

```python
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
```

- [ ] **Step 10: 테스트 통과 확인**

```bash
python -m pytest tests/test_job_store.py -v
```

Expected: 전체 통과

---

### Task 4: app.py — POST /jobs에서 source_bytes 저장 + config 노출

**Files:**
- Modify: `app.py`

- [ ] **Step 1: _state에 config 추가**

`create_app` 내 `_state` 딕셔너리에 `config` 추가:

```python
    _state: dict = {
        "store": store or InMemoryJobStore(),
        "prompt_store": prompt_store or InMemoryPromptStore(),
        "llm": AsyncMock(),
        "rag": AsyncMock(),
        "pool": None,
        "config": config,
    }
```

- [ ] **Step 2: create_job에서 source_bytes=raw 저장**

`create_job` 핸들러의 `store.create()` 호출 부분에 `source_bytes=raw` 추가:

```python
        job = await current_store.create(
            asset_type=asset_type,
            file_name=file.filename or "unknown",
            source_hash=source_hash,
            file_size=len(raw),
            source_bytes=raw,
            callback_url=callback_url,
            requested_by=requested_by,
            rag_mode=rag_mode,
        )
```

---

### Task 5: admin.py — retry 개선 + GET /admin/stats (TDD)

**Files:**
- Modify: `admin.py`
- Modify: `tests/test_admin.py`

- [ ] **Step 1: tests/test_admin.py 상단에 JobStatus 임포트 추가**

`tests/test_admin.py` 상단 임포트 블록에 추가:

```python
from models import JobStatus
```

- [ ] **Step 2: tests/test_admin.py에 개선된 retry 테스트 추가**

`tests/test_admin.py` 끝에 추가:

```python
# --- Group B: retry + stats 테스트 ---

async def test_retry_with_source_bytes(admin_client):
    """source_bytes 있는 job은 즉시 재처리 (소스 재업로드 불필요)."""
    from unittest.mock import patch, AsyncMock
    client, store, ps = admin_client
    await ps.seed_if_empty("plsql", "프롬프트")

    raw = b"PROCEDURE PROC_TEST IS BEGIN NULL; END;"
    job = await store.create(
        asset_type="plsql",
        file_name="t.sql",
        source_hash="h-retry",
        source_bytes=raw,
    )
    await store.save_error(job.id, "검증 실패")

    with patch("admin._safe_process", new_callable=AsyncMock):
        async with client:
            resp = await client.post(f"/admin/jobs/{job.id}/retry")

    assert resp.status_code == 200
    data = resp.json()
    assert "즉시 처리" in data["note"]
    assert data["job_id"] != job.id  # 새 job이 생성됨


async def test_retry_without_source_bytes(admin_client):
    """source_bytes 없는 기존 레코드는 안내 메시지 반환."""
    client, store, ps = admin_client
    job = await store.create(
        asset_type="plsql",
        file_name="t.sql",
        source_hash="h-no-bytes",
    )
    await store.save_error(job.id, "검증 실패")
    async with client:
        resp = await client.post(f"/admin/jobs/{job.id}/retry")
    assert resp.status_code == 200
    data = resp.json()
    assert "재업로드" in data["note"]


async def test_get_stats_empty(admin_client):
    client, store, ps = admin_client
    async with client:
        resp = await client.get("/admin/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["success_rate"] == 0.0
    assert data["recent_failures"] == []


async def test_get_stats_with_data(admin_client):
    client, store, ps = admin_client
    j1 = await store.create(asset_type="plsql", file_name="a.sql", source_hash="hs1")
    await store.update_status(j1.id, JobStatus.PROCESSING)
    await store.save_result(j1.id, "# result")

    j2 = await store.create(asset_type="plsql", file_name="b.sql", source_hash="hs2")
    await store.save_error(j2.id, "실패 에러")

    async with client:
        resp = await client.get("/admin/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["by_status"]["completed"] == 1
    assert data["by_status"]["failed"] == 1
    assert data["success_rate"] == 50.0
    assert len(data["recent_failures"]) == 1
```

- [ ] **Step 3: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_admin.py::test_retry_with_source_bytes tests/test_admin.py::test_retry_without_source_bytes tests/test_admin.py::test_get_stats_empty tests/test_admin.py::test_get_stats_with_data -v
```

Expected: FAIL

- [ ] **Step 4: admin.py — retry 로직 개선**

기존 `retry_job` 함수 전체를 교체:

```python
    @router.post("/jobs/{job_id}/retry", summary="Job 강제 재시도")
    async def retry_job(job_id: str):
        import asyncio
        import hashlib
        import time
        from models import JobStatus
        from worker import _safe_process

        state = get_state()
        store = state.store
        job = await store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status not in (JobStatus.FAILED,):
            raise HTTPException(status_code=400, detail="Only failed jobs can be retried")

        new_hash = hashlib.sha256(f"{job.source_hash}-retry-{time.time()}".encode()).hexdigest()

        if job.source_bytes is not None:
            new_job = await store.create(
                asset_type=job.asset_type,
                file_name=job.file_name,
                source_hash=new_hash,
                source_bytes=job.source_bytes,
                file_size=job.file_size,
                callback_url=job.callback_url,
                requested_by=job.requested_by,
                rag_mode=job.rag_mode,
            )
            asyncio.create_task(
                _safe_process(
                    job=new_job,
                    raw=job.source_bytes,
                    store=store,
                    config=state.config,
                    llm=state.llm,
                    rag=state.rag,
                    prompt_store=state.prompt_store,
                    rag_mode=job.rag_mode,
                )
            )
            return {"job_id": new_job.id, "status": new_job.status, "note": "재시도 job 생성됨. 즉시 처리 시작."}
        else:
            new_job = await store.create(
                asset_type=job.asset_type,
                file_name=job.file_name,
                source_hash=new_hash,
                callback_url=job.callback_url,
                requested_by=job.requested_by,
            )
            return {"job_id": new_job.id, "status": new_job.status, "note": "재시도 job 생성됨. 소스 재업로드 필요."}
```

- [ ] **Step 5: admin.py — GET /admin/stats 추가**

`create_admin_router` 내 `return router` 바로 위에 추가:

```python
    @router.get("/stats", summary="운영 통계")
    async def get_stats():
        state = get_state()
        store = state.store
        if not hasattr(store, "get_stats"):
            raise HTTPException(status_code=501, detail="get_stats not supported")
        return await store.get_stats()
```

- [ ] **Step 6: _StateProxy에 config 접근 가능한지 확인**

`app.py`의 `_StateProxy` 클래스 확인:

```python
    class _StateProxy:
        def __getattr__(self, key):
            return _state[key]
```

`_state["config"] = config`가 Task 4 Step 1에서 추가됐으므로 `state.config`로 접근 가능.

- [ ] **Step 7: 테스트 통과 확인**

```bash
python -m pytest tests/test_admin.py -v
```

Expected: 전체 통과

- [ ] **Step 8: 전체 테스트 회귀 확인**

```bash
python -m pytest tests/ -v
```

Expected: 전체 통과

---

### Task 6: 커밋 및 master merge

- [ ] **Step 1: 커밋**

```bash
git add schema.sql models.py job_store.py app.py admin.py tests/test_job_store.py tests/test_admin.py
git commit -m "feat: Group B — source_bytes 저장 + retry 자동화 + 운영 통계 API"
```

- [ ] **Step 2: master에 merge**

```bash
git checkout master
git merge feature/group-b
```

- [ ] **Step 3: 최종 전체 테스트 확인**

```bash
python -m pytest tests/ -v
curl http://localhost:8004/health
```
