# Group D — LightRAG RAG Mode 파라미터화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `POST /jobs`에 `rag_mode` 파라미터를 추가해 LightRAG query mode를 호출별로 지정할 수 있게 한다.

**Architecture:** `rag_mode`를 `rdoc_job` 테이블에 저장(추적 가능)하고, `app.py → worker.py → processor.py → rag_client.py`를 따라 전달한다. **이 브랜치는 Group C가 master에 merge된 후 master에서 생성한다.** Group B보다 먼저 배포되므로 이 브랜치에서 `source_bytes`와 `rag_mode` 컬럼을 모두 마이그레이션한다.

**Tech Stack:** Python 3.11+, FastAPI, asyncpg, pytest-asyncio

---

## File Map

| 파일 | 변경 | 내용 |
|------|------|------|
| `schema.sql` | Modify | `source_bytes BYTEA` + `rag_mode TEXT DEFAULT 'mix'` 컬럼 추가 |
| `models.py` | Modify | `Job`에 `rag_mode: str = "mix"` 필드 추가 |
| `job_store.py` | Modify | `create()` + `_row_to_job()`에 `rag_mode` 반영 |
| `app.py` | Modify | `POST /jobs`에 `rag_mode` Form 파라미터 + 유효성 검사 |
| `processor.py` | Modify | `to_reverse_doc()`에 `rag_mode` 파라미터 추가 |
| `worker.py` | Modify | `_safe_process()`에 `rag_mode` 파라미터 추가 |
| `tests/test_app.py` | Modify | rag_mode 유효/무효 테스트 추가 |
| `tests/test_processor.py` | Modify | rag.query() mode 전달 검증 추가 |

---

### Task 1: 브랜치 생성

- [ ] **Step 1: Group C merge 확인 후 브랜치 생성**

```bash
git checkout master && git pull
git checkout -b feature/group-d
```

---

### Task 2: 스키마 마이그레이션 + 모델 업데이트

**Files:**
- Modify: `schema.sql`
- Modify: `models.py`

- [ ] **Step 1: schema.sql에 두 컬럼 추가**

`schema.sql` 끝에 추가:

```sql
-- Group B+D 공유 마이그레이션: 먼저 배포하는 Group D에서 두 컬럼 모두 추가
ALTER TABLE rdoc_job ADD COLUMN IF NOT EXISTS source_bytes BYTEA;
ALTER TABLE rdoc_job ADD COLUMN IF NOT EXISTS rag_mode TEXT DEFAULT 'mix';
```

- [ ] **Step 2: models.py — Job에 rag_mode 필드 추가**

`models.py`의 `Job` 클래스에 `completed_at` 필드 아래 추가:

```python
    rag_mode: str = "mix"
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

### Task 3: job_store.py — rag_mode 반영

**Files:**
- Modify: `job_store.py`

- [ ] **Step 1: PostgresJobStore.create() 업데이트**

기존:
```python
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
```

교체:
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

- [ ] **Step 2: PostgresJobStore._row_to_job() 업데이트**

기존 `_row_to_job` 메서드의 `return Job(...)` 호출에 `rag_mode` 추가:

```python
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
            rag_mode=row.get("rag_mode") or "mix",
        )
```

---

### Task 4: processor.py + worker.py에 rag_mode 전달 (TDD)

**Files:**
- Modify: `processor.py`
- Modify: `worker.py`
- Modify: `tests/test_processor.py`

- [ ] **Step 1: tests/test_processor.py에 rag_mode 전달 테스트 추가**

`tests/test_processor.py` 끝에 추가:

```python
async def test_rag_mode_passed_to_query():
    """processor가 rag.query()에 rag_mode를 전달하는지 검증."""
    from unittest.mock import AsyncMock
    from processor import to_reverse_doc
    from job_store import InMemoryJobStore, InMemoryPromptStore

    store = InMemoryJobStore()
    job = await store.create(asset_type="plsql", file_name="t.sql", source_hash="h-mode-test")

    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value="# PROC_TEST\nTBL_LOAN_APPLICATION 처리")

    mock_rag = AsyncMock()
    mock_rag.query = AsyncMock(return_value="context")

    ps = InMemoryPromptStore()
    await ps.seed_if_empty("plsql", "테스트 프롬프트")

    raw = b"PROCEDURE PROC_TEST IS BEGIN SELECT * FROM TBL_LOAN_APPLICATION; END;"

    await to_reverse_doc(
        raw=raw,
        asset_type="plsql",
        job_id=job.id,
        file_name="t.sql",
        callback_url=None,
        store=store,
        llm=mock_llm,
        rag=mock_rag,
        prompt_store=ps,
        rag_mode="local",
    )

    mock_rag.query.assert_called_once()
    call_kwargs = mock_rag.query.call_args
    assert call_kwargs.kwargs.get("mode") == "local" or call_kwargs.args[1] == "local"
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_processor.py::test_rag_mode_passed_to_query -v
```

Expected: FAIL — `to_reverse_doc() got an unexpected keyword argument 'rag_mode'`

- [ ] **Step 3: processor.py — to_reverse_doc()에 rag_mode 추가**

`to_reverse_doc()` 시그니처 변경:

```python
async def to_reverse_doc(
    raw: bytes,
    asset_type: str,
    job_id: str,
    file_name: str,
    callback_url: str | None,
    store: JobStore,
    llm: LLMClient,
    rag: RAGClient,
    prompt_store,
    callback_field_map: str = "",
    callback_keep_unmapped: bool = True,
    rag_mode: str = "mix",
) -> None:
```

함수 내 RAG 쿼리 라인 변경:

```python
        # 기존:
        context = await rag.query(hint) if hint else ""
        # 변경:
        context = await rag.query(hint, mode=rag_mode) if hint else ""
```

- [ ] **Step 4: worker.py — _safe_process()에 rag_mode 추가**

```python
async def _safe_process(
    job: Job,
    raw: bytes,
    store: JobStore,
    config: Config,
    llm: LLMClient,
    rag: RAGClient,
    prompt_store,
    rag_mode: str = "mix",
) -> None:
    try:
        await to_reverse_doc(
            raw=raw,
            asset_type=job.asset_type,
            job_id=job.id,
            file_name=job.file_name,
            callback_url=job.callback_url,
            store=store,
            llm=llm,
            rag=rag,
            prompt_store=prompt_store,
            callback_field_map=config.callback_field_map,
            callback_keep_unmapped=config.callback_keep_unmapped,
            rag_mode=rag_mode,
        )
    except Exception:
        logger.exception("Unhandled error in job %s", job.id)
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
python -m pytest tests/test_processor.py::test_rag_mode_passed_to_query -v
```

Expected: PASSED

---

### Task 5: app.py — POST /jobs에 rag_mode 파라미터 추가 (TDD)

**Files:**
- Modify: `app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: tests/test_app.py에 rag_mode 테스트 추가**

`tests/test_app.py` 끝에 추가:

```python
# --- rag_mode 테스트 ---

async def test_post_jobs_default_rag_mode(app_client):
    """rag_mode 미지정 시 기본값 mix로 job 생성."""
    client, store, ps = app_client
    await ps.seed_if_empty("plsql", "프롬프트")
    content = b"PROCEDURE PROC_TEST IS BEGIN NULL; END;"
    with patch("app._safe_process", new_callable=AsyncMock):
        async with client:
            resp = await client.post(
                "/jobs",
                data={"asset_type": "plsql"},
                files={"file": ("t.sql", content, "text/plain")},
            )
    assert resp.status_code == 202


async def test_post_jobs_valid_rag_mode(app_client):
    """유효한 rag_mode 값으로 job 생성."""
    client, store, ps = app_client
    await ps.seed_if_empty("plsql", "프롬프트")
    content = b"PROCEDURE PROC_TEST IS BEGIN NULL; END;"
    with patch("app._safe_process", new_callable=AsyncMock):
        async with client:
            resp = await client.post(
                "/jobs",
                data={"asset_type": "plsql", "rag_mode": "local"},
                files={"file": ("t.sql", content, "text/plain")},
            )
    assert resp.status_code == 202


async def test_post_jobs_invalid_rag_mode(app_client):
    """유효하지 않은 rag_mode 값 → 400."""
    client, store, ps = app_client
    await ps.seed_if_empty("plsql", "프롬프트")
    content = b"PROCEDURE PROC_TEST IS BEGIN NULL; END;"
    async with client:
        resp = await client.post(
            "/jobs",
            data={"asset_type": "plsql", "rag_mode": "invalid_mode"},
            files={"file": ("t.sql", content, "text/plain")},
        )
    assert resp.status_code == 400
    assert "Invalid rag_mode" in resp.json()["detail"]
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_app.py::test_post_jobs_valid_rag_mode tests/test_app.py::test_post_jobs_invalid_rag_mode -v
```

Expected: `test_post_jobs_valid_rag_mode` — PASS (우연히), `test_post_jobs_invalid_rag_mode` — FAIL (400 아님)

- [ ] **Step 3: app.py — POST /jobs에 rag_mode 추가**

`app.py` 파일 상단 임포트 근처에 상수 추가 (SCHEMA_PATH 정의 바로 아래):

```python
VALID_RAG_MODES = frozenset({"local", "global", "hybrid", "mix", "naive"})
```

`create_job` 핸들러 시그니처 변경:

```python
    @app.post("/jobs", status_code=202)
    async def create_job(
        request: Request,
        file: UploadFile = File(...),
        asset_type: str = Form(...),
        callback_url: str | None = Form(None),
        requested_by: str | None = Form(None),
        rag_mode: str = Form("mix"),
    ):
```

파일 크기 체크 직후에 유효성 검사 추가:

```python
        if rag_mode not in VALID_RAG_MODES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid rag_mode: {rag_mode}. Must be one of: {', '.join(sorted(VALID_RAG_MODES))}",
            )
```

`store.create()` 호출에 `rag_mode` 추가:

```python
        job = await current_store.create(
            asset_type=asset_type,
            file_name=file.filename or "unknown",
            source_hash=source_hash,
            file_size=len(raw),
            callback_url=callback_url,
            requested_by=requested_by,
            rag_mode=rag_mode,
        )
```

`asyncio.create_task()` 호출에 `rag_mode` 추가:

```python
        asyncio.create_task(
            _safe_process(
                job=job,
                raw=raw,
                store=current_store,
                config=config,
                llm=_state["llm"],
                rag=_state["rag"],
                prompt_store=current_prompt_store,
                rag_mode=rag_mode,
            )
        )
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
python -m pytest tests/test_app.py::test_post_jobs_default_rag_mode tests/test_app.py::test_post_jobs_valid_rag_mode tests/test_app.py::test_post_jobs_invalid_rag_mode -v
```

Expected: 3 PASSED

- [ ] **Step 5: 전체 테스트 회귀 확인**

```bash
python -m pytest tests/ -v
```

Expected: 전체 통과

---

### Task 6: 커밋 및 master merge

- [ ] **Step 1: 커밋**

```bash
git add schema.sql models.py job_store.py app.py processor.py worker.py tests/test_app.py tests/test_processor.py
git commit -m "feat: Group D — rag_mode 파라미터화 (POST /jobs, DB 저장, 파이프라인 전달)"
```

- [ ] **Step 2: master에 merge**

```bash
git checkout master
git merge feature/group-d
```
