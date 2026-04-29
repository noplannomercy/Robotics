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


async def test_get_stats_empty(store):
    stats = await store.get_stats()
    assert stats["total"] == 0
    assert stats["success_rate"] == 0.0
    assert stats["retry_rate"] == 0.0
    assert stats["avg_processing_sec"] is None
    assert stats["recent_failures"] == []


async def test_get_stats_with_jobs(store):
    j1 = await store.create(asset_type="plsql", file_name="a.sql", source_hash="h1")
    j2 = await store.create(asset_type="plsql", file_name="b.sql", source_hash="h2")
    await store.update_status(j1.id, JobStatus.PROCESSING)
    await store.update_status(j2.id, JobStatus.PROCESSING)
    await store.save_result(j1.id, "# result1")
    await store.save_result(j2.id, "# result2")

    j3 = await store.create(asset_type="dictionary", file_name="c.sql", source_hash="h3")
    await store.save_error(j3.id, "검증 실패")

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
    await store.create(asset_type="plsql", file_name="a.sql", source_hash="h1")
    stats = await store.get_stats()
    assert stats["avg_processing_sec"] is None
