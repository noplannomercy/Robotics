import asyncio
import pytest
import httpx
from config import Config
from llm_client import LLMClient


@pytest.fixture
def config():
    return Config(
        llm_url="http://test-llm/v1/chat/completions",
        llm_model="test-model",
        llm_api_key="test-key",
        llm_timeout=10,
        llm_concurrency=2,
    )


@pytest.mark.asyncio
async def test_generate_success(config):
    mock_response = {
        "choices": [{"message": {"content": "생성된 역문서 내용"}}]
    }
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=mock_response)
    )
    async with LLMClient(config, transport=transport) as client:
        result = await client.generate(system="시스템 프롬프트", user="소스 코드")
    assert result == "생성된 역문서 내용"


@pytest.mark.asyncio
async def test_generate_strips_whitespace(config):
    mock_response = {
        "choices": [{"message": {"content": "  역문서\n  "}}]
    }
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=mock_response)
    )
    async with LLMClient(config, transport=transport) as client:
        result = await client.generate(system="sys", user="user")
    assert result == "역문서"


@pytest.mark.asyncio
async def test_generate_server_error_raises(config):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(500, text="Internal Server Error")
    )
    async with LLMClient(config, transport=transport) as client:
        with pytest.raises(Exception):
            await client.generate(system="sys", user="user")


@pytest.mark.asyncio
async def test_semaphore_limits_concurrency(config):
    """LLM_CONCURRENCY=2 이면 동시에 최대 2개만 실행."""
    active = 0
    max_active = 0
    lock = asyncio.Lock()

    class SlowAsyncTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            nonlocal active, max_active
            async with lock:
                active += 1
                max_active = max(max_active, active)
            await asyncio.sleep(0.05)
            async with lock:
                active -= 1
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    transport = SlowAsyncTransport()
    async with LLMClient(config, transport=transport) as client:
        tasks = [client.generate(system="s", user="u") for _ in range(5)]
        await asyncio.gather(*tasks)

    assert max_active <= 2
