# tests/test_callback.py
import json
import pytest
import httpx
from callback import send_callback, _apply_field_map

CALLBACK_URL = "http://ingestion-router/callback/forge"


def test_apply_field_map_protects_reserved_keys():
    """field_map이 rdoc_job_id/status/error를 rename·drop 못함 — 콜백 라우팅 계약 보호."""
    payload = {"rdoc_job_id": "j1", "status": "completed", "error": None, "content": "doc", "extra": "x"}
    # rdoc_job_id·status를 rename 시도 + keep_unmapped=False로 error·extra drop 유도
    fm = json.dumps({"rdoc_job_id": "id", "status": "state", "content": "text"})
    out = _apply_field_map(payload, fm, keep_unmapped=False)
    # reserved 3종은 원본 키로 보존돼야 함
    assert out["rdoc_job_id"] == "j1"
    assert out["status"] == "completed"
    assert "error" in out
    # non-reserved는 계약대로 동작 (content→text rename, extra는 drop)
    assert out["text"] == "doc"
    assert "extra" not in out


@pytest.mark.asyncio
async def test_send_callback_success():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"ok": True})
    )
    await send_callback(
        url=CALLBACK_URL,
        payload={"forge_job_id": "abc", "content": "# 역문서", "forge_status": "completed"},
        transport=transport,
    )


@pytest.mark.asyncio
async def test_send_callback_no_url_skips():
    await send_callback(url=None, payload={"forge_job_id": "x"})


@pytest.mark.asyncio
async def test_send_callback_retry_on_failure():
    call_count = 0

    def flaky_handler(request):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(500, text="error")
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(flaky_handler)
    await send_callback(
        url=CALLBACK_URL,
        payload={"forge_job_id": "abc", "content": "ok", "forge_status": "completed"},
        transport=transport,
        delays=[0, 0, 0],
    )
    assert call_count == 3


@pytest.mark.asyncio
async def test_send_callback_all_retries_fail_no_raise():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(500, text="always fails")
    )
    await send_callback(
        url=CALLBACK_URL,
        payload={"forge_job_id": "abc", "content": "x", "forge_status": "failed"},
        transport=transport,
        delays=[0, 0, 0],
    )
