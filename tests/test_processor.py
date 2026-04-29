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
        file_name="PKG_TEST.sql",
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
            return "역문서 내용 (식별자 누락)"
        return "PROC_MISSING은 TBL_DATA.STATUS = 'OK'로 처리한다."

    llm = AsyncMock()
    llm.generate = mock_generate
    rag = AsyncMock()
    rag.query = AsyncMock(return_value="")

    await to_reverse_doc(
        raw=b"PROCEDURE PROC_MISSING IS BEGIN SELECT STATUS FROM TBL_DATA; END;",
        asset_type="plsql",
        job_id=job.id,
        file_name="f.sql",
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
        file_name="f.sql",
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
        file_name="f.sql",
        callback_url=None,
        store=store,
        llm=llm,
        rag=rag,
        prompt_store=prompt_store,
    )

    updated = await store.get(job.id)
    assert updated.status == JobStatus.COMPLETED
    llm.generate.assert_called_once()  # LLM은 한 번 호출됨


async def test_rag_mode_passed_to_query():
    """processor가 rag.query()에 rag_mode를 전달하는지 검증."""
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
