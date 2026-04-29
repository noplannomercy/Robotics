import pytest
import httpx
from app import create_app
from job_store import InMemoryJobStore, InMemoryPromptStore
from config import Config


@pytest.fixture
def admin_client():
    config = Config(llm_url="http://mock", lightrag_url="http://mock")
    store = InMemoryJobStore()
    prompt_store = InMemoryPromptStore()
    app = create_app(store=store, config=config, prompt_store=prompt_store)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test"), store, prompt_store


# --- InMemoryPromptStore 메서드 단위 테스트 ---

async def test_list_versions_empty():
    ps = InMemoryPromptStore()
    result = await ps.list_versions("plsql")
    assert result == []


async def test_list_versions_multiple():
    ps = InMemoryPromptStore()
    await ps.create_version("plsql", "v1 text")
    await ps.create_version("plsql", "v2 text")
    versions = await ps.list_versions("plsql")
    assert len(versions) == 2
    nums = {v["version"] for v in versions}
    assert nums == {1, 2}
    for v in versions:
        assert "text" not in v


async def test_get_version_exists():
    ps = InMemoryPromptStore()
    await ps.create_version("plsql", "v1 text")
    await ps.create_version("plsql", "v2 text")
    result = await ps.get_version("plsql", 1)
    assert result is not None
    assert result["version"] == 1
    assert result["text"] == "v1 text"


async def test_get_version_not_found():
    ps = InMemoryPromptStore()
    await ps.create_version("plsql", "v1 text")
    result = await ps.get_version("plsql", 99)
    assert result is None


# --- Admin 엔드포인트 테스트 ---

async def test_get_active_prompt_ok(admin_client):
    client, store, ps = admin_client
    await ps.create_version("plsql", "테스트 프롬프트 v1")
    async with client:
        resp = await client.get("/admin/prompts/plsql")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == 1
    assert data["text"] == "테스트 프롬프트 v1"
    assert data["is_active"] is True


async def test_get_active_prompt_not_found(admin_client):
    client, store, ps = admin_client
    async with client:
        resp = await client.get("/admin/prompts/unknown_type")
    assert resp.status_code == 404


async def test_list_prompt_history_ok(admin_client):
    client, store, ps = admin_client
    await ps.create_version("plsql", "v1 text")
    await ps.create_version("plsql", "v2 text")
    async with client:
        resp = await client.get("/admin/prompts/plsql/history")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["versions"]) == 2
    for v in data["versions"]:
        assert "text" not in v


async def test_get_prompt_version_ok(admin_client):
    client, store, ps = admin_client
    await ps.create_version("plsql", "첫 번째 버전")
    async with client:
        resp = await client.get("/admin/prompts/plsql/history/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == 1
    assert data["text"] == "첫 번째 버전"


async def test_get_prompt_version_not_found(admin_client):
    client, store, ps = admin_client
    await ps.create_version("plsql", "v1")
    async with client:
        resp = await client.get("/admin/prompts/plsql/history/99")
    assert resp.status_code == 404


async def test_rollback_prompt_ok(admin_client):
    client, store, ps = admin_client
    await ps.create_version("plsql", "v1 text")
    await ps.create_version("plsql", "v2 text")  # v2가 현재 활성
    async with client:
        resp = await client.post("/admin/prompts/plsql/rollback/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["new_version"] == 3
    assert data["rolled_back_from"] == 1
    # 새 버전(v3)이 활성화됐는지 확인
    active = await ps.get_active("plsql")
    assert active["version"] == 3
    assert active["text"] == "v1 text"
    # v2는 비활성화
    v2 = await ps.get_version("plsql", 2)
    assert v2["is_active"] is False


async def test_rollback_prompt_version_not_found(admin_client):
    client, store, ps = admin_client
    await ps.create_version("plsql", "v1")
    async with client:
        resp = await client.post("/admin/prompts/plsql/rollback/99")
    assert resp.status_code == 404
