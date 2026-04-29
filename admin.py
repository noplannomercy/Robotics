# admin.py
from fastapi import APIRouter, Body, Depends, HTTPException, Query


def create_admin_router(get_state, auth_dep) -> APIRouter:
    router = APIRouter(dependencies=[Depends(auth_dep)], tags=["관리"])

    @router.get("/jobs", summary="Job 목록")
    async def list_jobs(
        status: str | None = Query(None),
        asset_type: str | None = Query(None),
        page: int = Query(1, ge=1),
        size: int = Query(20, ge=1, le=100),
    ):
        state = get_state()
        store = state.store
        if not hasattr(store, "list_jobs"):
            raise HTTPException(status_code=501, detail="list_jobs not supported")
        jobs, total = await store.list_jobs(
            page=page, size=size, status=status, asset_type=asset_type
        )
        return {"jobs": jobs, "total": total, "page": page, "size": size}

    @router.post("/jobs/{job_id}/retry", summary="Job 강제 재시도")
    async def retry_job(job_id: str):
        import asyncio
        import hashlib
        import time
        from models import JobStatus
        from worker import _safe_process

        state = get_state()
        store = state.store
        job = await store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status not in (JobStatus.FAILED,):
            raise HTTPException(status_code=400, detail="Only failed jobs can be retried")

        new_hash = hashlib.sha256(f"{job.source_hash}-retry-{time.time()}".encode()).hexdigest()
        new_job = await store.create(
            asset_type=job.asset_type,
            file_name=job.file_name,
            source_hash=new_hash,
            callback_url=job.callback_url,
            requested_by=job.requested_by,
        )

        return {"job_id": new_job.id, "status": new_job.status, "note": "재시도 job 생성됨. 소스 재업로드 필요."}

    @router.put("/prompts/{asset_type}", summary="프롬프트 새 버전 등록")
    async def update_prompt(asset_type: str, text: str = Body(..., embed=True)):
        state = get_state()
        prompt_store = state.prompt_store
        result = await prompt_store.create_version(asset_type, text)
        return {"asset_type": asset_type, "version": result["version"], "is_active": result["is_active"]}

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

    return router
