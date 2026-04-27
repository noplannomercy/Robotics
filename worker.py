# worker.py
import asyncio
import logging

from config import Config
from job_store import JobStore
from llm_client import LLMClient
from models import Job
from processor import to_reverse_doc
from rag_client import RAGClient

logger = logging.getLogger(__name__)


async def _safe_process(
    job: Job,
    raw: bytes,
    store: JobStore,
    config: Config,
    llm: LLMClient,
    rag: RAGClient,
    prompt_store,
) -> None:
    """asyncio.create_task용 래퍼. 미처리 예외를 로깅."""
    try:
        await to_reverse_doc(
            raw=raw,
            asset_type=job.asset_type,
            job_id=job.id,
            callback_url=job.callback_url,
            store=store,
            llm=llm,
            rag=rag,
            prompt_store=prompt_store,
        )
    except Exception:
        logger.exception("Unhandled error in job %s", job.id)
