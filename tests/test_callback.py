# tests/test_callback.py
import pytest
import httpx
from callback import send_callback

CALLBACK_URL = "http://ingestion-router/callback/forge"


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
