# Group A — 프롬프트 관리 강화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 현재 등록만 가능한 프롬프트 관리를 조회/히스토리/롤백까지 확장한다.

**Architecture:** `InMemoryPromptStore`와 `PromptStore` 양쪽에 `list_versions()`, `get_version()` 메서드를 추가하고, `admin.py`에 4개 엔드포인트를 추가한다. 스키마 변경 없음. 순차 merge 전략: **이 브랜치는 master에서 생성, master에 merge 완료 후 Group C 브랜치 생성.**

**Tech Stack:** Python 3.11+, FastAPI, asyncpg, pytest-asyncio

---

## File Map

| 파일 | 변경 | 내용 |
|------|------|------|
| `job_store.py` | Modify | `InMemoryPromptStore`와 `PromptStore`에 `list_versions()`, `get_version()` 추가 |
| `admin.py` | Modify | 4개 엔드포인트 추가 |
| `tests/test_admin.py` | Create | Group A 단위 테스트 전체 |

---

### Task 1: 브랜치 생성

- [ ] **Step 1: master 최신 상태 확인 후 브랜치 생성**

```bash
git checkout master && git pull
git checkout -b feature/group-a
```

---

### Task 2: InMemoryPromptStore에 list_versions() + get_version() 추가 (TDD)

**Files:**
- Modify: `job_store.py`
- Create: `tests/test_admin.py`

- [ ] **Step 1: 테스트 파일 생성 및 실패 테스트 작성**

```python
# tests/test_admin.py
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
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_admin.py::test_list_versions_empty tests/test_admin.py::test_list_versions_multiple tests/test_admin.py::test_get_version_exists tests/test_admin.py::test_get_version_not_found -v
```

Expected: FAIL — `AttributeError: 'InMemoryPromptStore' object has no attribute 'list_versions'`

- [ ] **Step 3: job_store.py — InMemoryPromptStore에 두 메서드 추가**

`InMemoryPromptStore` 클래스 끝에 추가 (기존 `create_version` 메서드 아래):

```python
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
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
python -m pytest tests/test_admin.py::test_list_versions_empty tests/test_admin.py::test_list_versions_multiple tests/test_admin.py::test_get_version_exists tests/test_admin.py::test_get_version_not_found -v
```

Expected: 4 PASSED

---

### Task 3: PromptStore(PostgreSQL)에 동일 메서드 추가

**Files:**
- Modify: `job_store.py`

- [ ] **Step 1: job_store.py — PromptStore 클래스에 두 메서드 추가**

`PromptStore` 클래스의 `create_version` 메서드 아래에 추가:

```python
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
```

> PostgreSQL 메서드는 DB 없이 단위 테스트 불가 — InMemoryPromptStore 테스트가 인터페이스 검증을 담당.

---

### Task 4: admin.py에 4개 엔드포인트 추가 (TDD)

**Files:**
- Modify: `admin.py`
- Modify: `tests/test_admin.py`

- [ ] **Step 1: tests/test_admin.py에 엔드포인트 테스트 추가**

`tests/test_admin.py` 끝에 추가:

```python
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
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_admin.py -k "get_active_prompt or list_prompt_history or get_prompt_version or rollback_prompt" -v
```

Expected: FAIL — `404 Not Found` (엔드포인트 없음)

- [ ] **Step 3: admin.py에 4개 엔드포인트 추가**

`create_admin_router` 함수 내 `return router` 바로 위에 추가:

```python
    @router.get("/prompts/{asset_type}", summary="활성 프롬프트 조회")
    async def get_active_prompt(asset_type: str):
        state = get_state()
        prompt = await state.prompt_store.get_active(asset_type)
        if prompt is None:
            raise HTTPException(status_code=404, detail=f"No active prompt for asset_type: {asset_type}")
        return {
            "asset_type": asset_type,
            "version": prompt["version"],
            "text": prompt["text"],
            "is_active": prompt["is_active"],
            "created_at": str(prompt.get("created_at") or ""),
        }

    @router.get("/prompts/{asset_type}/history", summary="프롬프트 버전 목록")
    async def list_prompt_history(asset_type: str):
        state = get_state()
        if not hasattr(state.prompt_store, "list_versions"):
            raise HTTPException(status_code=501, detail="list_versions not supported")
        versions = await state.prompt_store.list_versions(asset_type)
        return {"asset_type": asset_type, "versions": versions}

    @router.get("/prompts/{asset_type}/history/{version}", summary="특정 버전 조회")
    async def get_prompt_version(asset_type: str, version: int):
        state = get_state()
        if not hasattr(state.prompt_store, "get_version"):
            raise HTTPException(status_code=501, detail="get_version not supported")
        prompt = await state.prompt_store.get_version(asset_type, version)
        if prompt is None:
            raise HTTPException(status_code=404, detail=f"Version {version} not found for asset_type: {asset_type}")
        return {
            "asset_type": asset_type,
            "version": prompt["version"],
            "text": prompt["text"],
            "is_active": prompt["is_active"],
            "created_at": str(prompt.get("created_at") or ""),
        }

    @router.post("/prompts/{asset_type}/rollback/{version}", summary="버전 롤백")
    async def rollback_prompt(asset_type: str, version: int):
        state = get_state()
        if not hasattr(state.prompt_store, "get_version"):
            raise HTTPException(status_code=501, detail="get_version not supported")
        target = await state.prompt_store.get_version(asset_type, version)
        if target is None:
            raise HTTPException(status_code=404, detail=f"Version {version} not found for asset_type: {asset_type}")
        new = await state.prompt_store.create_version(asset_type, target["text"])
        return {"asset_type": asset_type, "new_version": new["version"], "rolled_back_from": version}
```

- [ ] **Step 4: 전체 테스트 실행 — 통과 확인**

```bash
python -m pytest tests/test_admin.py -v
```

Expected: 모든 테스트 PASSED

- [ ] **Step 5: 기존 테스트 회귀 확인**

```bash
python -m pytest tests/ -v
```

Expected: 전체 통과

---

### Task 5: 커밋 및 master merge

- [ ] **Step 1: 커밋**

```bash
git add job_store.py admin.py tests/test_admin.py
git commit -m "feat: Group A — 프롬프트 관리 강화 (조회/히스토리/롤백)"
```

- [ ] **Step 2: master에 merge**

```bash
git checkout master
git merge feature/group-a
```
