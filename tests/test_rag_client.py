import pytest
import httpx
from config import Config
from rag_client import RAGClient


@pytest.fixture
def config():
    return Config(
        lightrag_url="http://test-rag",
        lightrag_api_key="test-key",
        rag_timeout=5,
    )


@pytest.mark.asyncio
async def test_query_success(config):
    mock_response = {"response": "TBL_LOAN_APPLICATION은 대출 신청 테이블..."}
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=mock_response)
    )
    async with RAGClient(config, transport=transport) as client:
        result = await client.query("PKG_AUTO_LOAN_APPROVAL TBL_LOAN_APPLICATION")
    assert "TBL_LOAN_APPLICATION" in result


@pytest.mark.asyncio
async def test_query_connection_error_returns_empty(config):
    def raise_error(request):
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(raise_error)
    async with RAGClient(config, transport=transport) as client:
        result = await client.query("PKG_TEST")
    assert result == ""


@pytest.mark.asyncio
async def test_query_timeout_returns_empty(config):
    def raise_timeout(request):
        raise httpx.TimeoutException("timeout")

    transport = httpx.MockTransport(raise_timeout)
    async with RAGClient(config, transport=transport) as client:
        result = await client.query("PKG_TEST")
    assert result == ""


@pytest.mark.asyncio
async def test_query_empty_kb_returns_empty(config):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"response": ""})
    )
    async with RAGClient(config, transport=transport) as client:
        result = await client.query("PKG_TEST")
    assert result == ""
