# tests/test_e2e.py
"""
Mock E2E: POST /jobs → worker 비동기 실행 → GET /jobs/{id}/result 전체 흐름.
실제 LLM/LightRAG 없이 MockTransport + InMemoryJobStore로 검증.
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

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # POST /jobs (patch _safe_process so it doesn't actually run in background)
        with patch("app._safe_process") as mock_sp:
            mock_sp.return_value = None

            resp = await client.post(
                "/jobs",
                data={"asset_type": "plsql"},
                files={"file": ("test.sql", source, "text/plain")},
            )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        # Simulate worker directly
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
            file_name="test.sql",
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

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
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

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/jobs",
            data={"asset_type": "plsql"},
            files={"file": ("big.sql", large_source, "text/plain")},
        )
    assert resp.status_code == 413
