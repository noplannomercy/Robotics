# processor.py
import hashlib
import logging
import re

from callback import send_callback
from job_store import JobStore
from llm_client import LLMClient
from models import JobStatus
from rag_client import RAGClient
from validator import validate

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
PROJECT_ID_RE = re.compile(r'(?<![A-Z0-9_])(?:TBL|PROC|FUNC|PKG|SEQ|FK|PK)_[A-Z0-9_]+(?![A-Z0-9_])')


def extract_hint_keywords(source: str | bytes) -> str:
    """소스에서 project 식별자만 추출해 RAG 쿼리 힌트 생성."""
    if isinstance(source, bytes):
        source = source.decode("utf-8", errors="replace")
    ids = sorted(set(PROJECT_ID_RE.findall(source)))
    return " ".join(ids)


def compute_source_hash(source: bytes, prompt_version: str) -> str:
    return hashlib.sha256(source + prompt_version.encode()).hexdigest()


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
) -> None:
    """역문서화 파이프라인. 결과를 store에 저장하고 callback 전송."""
    await store.update_status(job_id, JobStatus.PROCESSING)

    try:
        # 1. 프롬프트 조회
        prompt_info = await prompt_store.get_active(asset_type)
        if prompt_info is None:
            raise ValueError(f"No active prompt for asset_type: {asset_type}")
        system_prompt = prompt_info["text"]

        # 2. RAG context 조회
        hint = extract_hint_keywords(raw)
        context = await rag.query(hint) if hint else ""
        if not context:
            logger.warning("Empty RAG context for job %s (asset_type=%s)", job_id, asset_type)

        # 3. LLM 생성 + 검증 (최대 MAX_RETRIES회)
        source_text = raw.decode("utf-8", errors="replace")
        user_content = f"[원문]\n{source_text}\n\n[참조 컨텍스트]\n{context}"
        result = None
        last_feedback = None

        for attempt in range(MAX_RETRIES):
            await store.increment_attempts(job_id)

            prompt_with_feedback = system_prompt
            if last_feedback:
                prompt_with_feedback += f"\n\n## 재시도 피드백\n{last_feedback}"

            result = await llm.generate(system=prompt_with_feedback, user=user_content)

            verdict = validate(raw=source_text, reverse=result)
            if verdict.passed:
                break
            last_feedback = verdict.feedback
            logger.warning(
                "Job %s attempt %d validation failed: %s",
                job_id, attempt + 1, verdict.feedback,
            )
        else:
            # 3회 모두 실패
            await store.save_error(job_id, f"검증 실패 (3회): {last_feedback}")
            await send_callback(
                url=callback_url,
                payload={"rdoc_job_id": job_id, "file_name": file_name, "content": "", "status": "failed", "error": last_feedback},
                field_map=callback_field_map,
                keep_unmapped=callback_keep_unmapped,
            )
            return

        # 4. 결과 저장
        await store.save_result(job_id, result)

        # 5. Callback 전송
        await send_callback(
            url=callback_url,
            payload={"rdoc_job_id": job_id, "file_name": file_name, "content": result, "status": "completed", "error": None},
            field_map=callback_field_map,
            keep_unmapped=callback_keep_unmapped,
        )

    except Exception as e:
        logger.exception("Unexpected error in job %s", job_id)
        await store.save_error(job_id, str(e))
        await send_callback(
            url=callback_url,
            payload={"rdoc_job_id": job_id, "file_name": file_name, "content": "", "status": "failed", "error": str(e)},
            field_map=callback_field_map,
            keep_unmapped=callback_keep_unmapped,
        )
