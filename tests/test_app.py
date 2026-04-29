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
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test"), store, prompt_store


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


# --- count_by_status 단위 테스트 ---

async def test_count_by_status_empty():
    store = InMemoryJobStore()
    counts = await store.count_by_status(["queued", "processing"])
    assert counts == {"queued": 0, "processing": 0}


async def test_count_by_status_with_jobs():
    store = InMemoryJobStore()
    await store.create(asset_type="plsql", file_name="a.sql", source_hash="h1")
    await store.create(asset_type="plsql", file_name="b.sql", source_hash="h2")
    job3 = await store.create(asset_type="plsql", file_name="c.sql", source_hash="h3")
    await store.update_status(job3.id, JobStatus.PROCESSING)
    counts = await store.count_by_status(["queued", "processing"])
    assert counts["queued"] == 2
    assert counts["processing"] == 1


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
    await store.create(asset_type="plsql", file_name="a.sql", source_hash="h1")
    await store.create(asset_type="plsql", file_name="b.sql", source_hash="h2")
    async with client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["queue"]["queued"] == 2
    assert data["queue"]["processing"] == 0


async def test_health_db_failure_returns_503():
    """PostgresJobStore의 count_by_status가 실패하면 503을 반환해야 한다."""
    from unittest.mock import AsyncMock, MagicMock
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
