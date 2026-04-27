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
