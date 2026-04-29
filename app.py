# app.py
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile

from auth import verify_api_key
from config import Config
from job_store import InMemoryJobStore, InMemoryPromptStore, JobStore
from models import JobStatus
from processor import compute_source_hash
from prompts import seed_prompts
from worker import _safe_process

logger = logging.getLogger(__name__)

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


async def _apply_schema(pool) -> None:
    if not os.path.isfile(SCHEMA_PATH):
        logger.warning("schema.sql not found, skipping")
        return
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        ddl = f.read()
    async with pool.acquire() as conn:
        await conn.execute(ddl)
    logger.info("schema.sql applied")


def create_app(
    store: JobStore | None = None,
    config: Config | None = None,
    prompt_store=None,
) -> FastAPI:
    config = config or Config()

    # Mutable state container — initialized at creation, updated by lifespan
    _state: dict = {
        "store": store or InMemoryJobStore(),
        "prompt_store": prompt_store or InMemoryPromptStore(),
        "llm": AsyncMock(),
        "rag": AsyncMock(),
        "pool": None,
    }

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if config.database_url:
            import asyncpg
            from job_store import PostgresJobStore, PromptStore
            from llm_client import LLMClient
            from rag_client import RAGClient

            pool = await asyncpg.create_pool(config.database_url)
            _state["pool"] = pool
            await _apply_schema(pool)
            _state["store"] = PostgresJobStore(pool)
            _state["prompt_store"] = PromptStore(pool)
            _state["llm"] = LLMClient(config)
            _state["rag"] = RAGClient(config)

        await seed_prompts(_state["prompt_store"])

        # Also expose on app.state for compatibility
        app.state.store = _state["store"]
        app.state.prompt_store = _state["prompt_store"]
        app.state.llm = _state["llm"]
        app.state.rag = _state["rag"]

        yield

        if hasattr(_state["llm"], "close"):
            await _state["llm"].close()
        if hasattr(_state["rag"], "close"):
            await _state["rag"].close()
        if _state["pool"] is not None:
            await _state["pool"].close()

    app = FastAPI(title="Reverse-Doc Service", version="1.0.0", lifespan=lifespan)

    from admin import create_admin_router
    auth_dep = verify_api_key(config)
    class _StateProxy:
        def __getattr__(self, key):
            return _state[key]

    admin_router = create_admin_router(lambda: _StateProxy(), auth_dep)
    app.include_router(admin_router, prefix="/admin")

    @app.get("/health")
    async def health():
        from fastapi.responses import JSONResponse
        from job_store import PostgresJobStore

        store = _state["store"]

        try:
            counts = await store.count_by_status(["queued", "processing"])
        except Exception:
            if isinstance(store, PostgresJobStore):
                return JSONResponse(
                    status_code=503,
                    content={"status": "unavailable", "reason": "db"},
                )
            counts = {"queued": 0, "processing": 0}

        return {
            "status": "ok",
            "queue": {
                "queued": counts.get("queued", 0),
                "processing": counts.get("processing", 0),
            },
        }

    @app.post("/jobs", status_code=202)
    async def create_job(
        request: Request,
        file: UploadFile = File(...),
        asset_type: str = Form(...),
        callback_url: str | None = Form(None),
        requested_by: str | None = Form(None),
    ):
        raw = await file.read()
        if len(raw) > config.max_file_size_kb * 1024:
            raise HTTPException(status_code=413, detail=f"File exceeds {config.max_file_size_kb}KB limit")

        current_store = _state["store"]
        current_prompt_store = _state["prompt_store"]

        prompt_info = await current_prompt_store.get_active(asset_type)
        if prompt_info is None:
            raise HTTPException(status_code=400, detail=f"Unsupported asset_type: {asset_type}")

        prompt_version = str(prompt_info.get("version", "1"))
        source_hash = compute_source_hash(raw, prompt_version)

        existing = await current_store.get_by_hash(source_hash)
        if existing:
            return {"job_id": existing.id, "status": existing.status, "cached": True}

        job = await current_store.create(
            asset_type=asset_type,
            file_name=file.filename or "unknown",
            source_hash=source_hash,
            file_size=len(raw),
            callback_url=callback_url,
            requested_by=requested_by,
        )

        asyncio.create_task(
            _safe_process(
                job=job,
                raw=raw,
                store=current_store,
                config=config,
                llm=_state["llm"],
                rag=_state["rag"],
                prompt_store=current_prompt_store,
            )
        )

        return {"job_id": job.id, "status": job.status}

    @app.get("/jobs/{job_id}")
    async def get_job(job_id: str):
        job = await _state["store"].get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return {
            "job_id": job.id,
            "status": job.status,
            "asset_type": job.asset_type,
            "file_name": job.file_name,
            "attempts": job.attempts,
            "error": job.error,
            "created_at": str(job.created_at),
            "started_at": str(job.started_at) if job.started_at else None,
            "completed_at": str(job.completed_at) if job.completed_at else None,
        }

    @app.get("/jobs/{job_id}/result")
    async def get_job_result(job_id: str):
        job = await _state["store"].get(job_id)
        if job is None or job.status != JobStatus.COMPLETED:
            raise HTTPException(status_code=404, detail="Job not completed or not found")
        return {"job_id": job.id, "status": job.status, "result": job.result}

    @app.delete("/jobs/{job_id}", status_code=204)
    async def delete_job(job_id: str):
        job = await _state["store"].get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        await _state["store"].delete(job_id)

    return app
