# Group C — 운영/모니터링 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/health`를 강화해 DB 연결 실패 시 503을 반환하고 큐 현황을 포함한다.

**Architecture:** `JobStore` ABC와 두 구현체에 경량 `count_by_status()` 메서드를 추가하고 `/health` 핸들러를 업데이트한다. 스키마 변경 없음. **이 브랜치는 Group A가 master에 merge된 후 master에서 생성한다.**

**Tech Stack:** Python 3.11+, FastAPI, asyncpg, pytest-asyncio

---

## File Map

| 파일 | 변경 | 내용 |
|------|------|------|
| `job_store.py` | Modify | `JobStore` ABC + `InMemoryJobStore` + `PostgresJobStore`에 `count_by_status()` 추가 |
| `app.py` | Modify | `/health` 핸들러 강화 |
| `tests/test_app.py` | Modify | health 테스트 추가 |

---

### Task 1: 브랜치 생성

- [ ] **Step 1: Group A merge 확인 후 브랜치 생성**

```bash
git checkout master && git pull
git checkout -b feature/group-c
```

---

### Task 2: count_by_status() 추가 (TDD)

**Files:**
- Modify: `job_store.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: tests/test_app.py에 count_by_status 단위 테스트 추가**

`tests/test_app.py` 끝에 추가:

```python
# --- count_by_status 단위 테스트 ---

async def test_count_by_status_empty():
    store = InMemoryJobStore()
    counts = await store.count_by_status(["queued", "processing"])
    assert counts == {"queued": 0, "processing": 0}


async def test_count_by_status_with_jobs():
    from job_store import InMemoryJobStore
    store = InMemoryJobStore()
    await store.create(asset_type="plsql", file_name="a.sql", source_hash="h1")
    await store.create(asset_type="plsql", file_name="b.sql", source_hash="h2")
    job3 = await store.create(asset_type="plsql", file_name="c.sql", source_hash="h3")
    await store.update_status(job3.id, JobStatus.PROCESSING)
    counts = await store.count_by_status(["queued", "processing"])
    assert counts["queued"] == 2
    assert counts["processing"] == 1
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_app.py::test_count_by_status_empty tests/test_app.py::test_count_by_status_with_jobs -v
```

Expected: FAIL — `AttributeError: 'InMemoryJobStore' object has no attribute 'count_by_status'`

- [ ] **Step 3: job_store.py — JobStore ABC에 추상 메서드 추가**

`JobStore` 클래스의 `delete` 메서드 아래에 추가:

```python
    @abstractmethod
    async def count_by_status(self, statuses: list[str]) -> dict[str, int]: ...
```

- [ ] **Step 4: job_store.py — InMemoryJobStore에 구현 추가**

`InMemoryJobStore`의 `delete` 메서드 아래에 추가:

```python
    async def count_by_status(self, statuses: list[str]) -> dict[str, int]:
        result = {s: 0 for s in statuses}
        for job in self._jobs.values():
            if job.status in result:
                result[job.status] += 1
        return result
```

- [ ] **Step 5: job_store.py — PostgresJobStore에 구현 추가**

`PostgresJobStore`의 `delete` 메서드 아래에 추가:

```python
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
```

- [ ] **Step 6: 테스트 실행 — 통과 확인**

```bash
python -m pytest tests/test_app.py::test_count_by_status_empty tests/test_app.py::test_count_by_status_with_jobs -v
```

Expected: 2 PASSED

---

### Task 3: /health 핸들러 강화 (TDD)

**Files:**
- Modify: `app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: tests/test_app.py에 강화된 health 테스트 추가**

`tests/test_app.py` 끝에 추가:

```python
# --- 강화된 /health 테스트 ---

async def test_health_includes_queue(app_client):
    client, store, ps = app_client
    async with client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "queue" in data
    assert "queued" in data["queue"]
    assert "processing" in data["queue"]


async def test_health_queue_counts_jobs(app_client):
    client, store, ps = app_client
    # queued job 2개 생성
    j1 = await store.create(asset_type="plsql", file_name="a.sql", source_hash="h1")
    j2 = await store.create(asset_type="plsql", file_name="b.sql", source_hash="h2")
    async with client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["queue"]["queued"] == 2
    assert data["queue"]["processing"] == 0


async def test_health_db_failure_returns_503():
    """PostgresJobStore의 count_by_status가 실패하면 503을 반환해야 한다."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from job_store import PostgresJobStore

    mock_pool = MagicMock()
    mock_pool.fetch = AsyncMock(side_effect=Exception("DB connection failed"))
    mock_pool.acquire = MagicMock()
    mock_pool.close = AsyncMock()

    pg_store = PostgresJobStore(mock_pool)

    config = Config(database_url="postgresql://mock", llm_url="http://mock", lightrag_url="http://mock")
    app = create_app(store=pg_store, config=config)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")

    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "unavailable"
    assert data["reason"] == "db"
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_app.py::test_health_includes_queue tests/test_app.py::test_health_queue_counts_jobs tests/test_app.py::test_health_db_failure_returns_503 -v
```

Expected: `test_health_includes_queue` — FAIL (응답에 queue 없음), 나머지도 FAIL

- [ ] **Step 3: app.py — /health 핸들러 교체**

`app.py`에서 기존 `/health` 핸들러:

```python
    @app.get("/health")
    async def health():
        return {"status": "ok"}
```

를 아래로 교체:

```python
    @app.get("/health")
    async def health():
        from fastapi.responses import JSONResponse

        store = _state["store"]
        pool = _state["pool"]

        try:
            counts = await store.count_by_status(["queued", "processing"])
        except Exception:
            if pool is not None:
                return JSONResponse(
                    status_code=503,
                    content={"status": "unavailable", "reason": "db"},
                )
            counts = {"queued": 0, "processing": 0}

        return {
            "status": "ok",
            "queue": {
                "queued": counts.get("queued", 0),
                "processing": counts.get("processing", 0),
            },
        }
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
python -m pytest tests/test_app.py::test_health_includes_queue tests/test_app.py::test_health_queue_counts_jobs tests/test_app.py::test_health_db_failure_returns_503 -v
```

Expected: 3 PASSED

- [ ] **Step 5: 전체 테스트 회귀 확인**

```bash
python -m pytest tests/ -v
```

Expected: 전체 통과

---

### Task 4: 커밋 및 master merge

- [ ] **Step 1: 커밋**

```bash
git add job_store.py app.py tests/test_app.py
git commit -m "feat: Group C — /health 강화 (queue 카운트, DB 실패 503)"
```

- [ ] **Step 2: master에 merge**

```bash
git checkout master
git merge feature/group-c
```
