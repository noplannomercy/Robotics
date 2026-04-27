import logging

import httpx

from config import Config

logger = logging.getLogger(__name__)


class RAGClient:
    def __init__(self, config: Config, transport: httpx.AsyncBaseTransport | None = None):
        self.config = config
        headers = {}
        if config.lightrag_api_key:
            headers["Authorization"] = f"Bearer {config.lightrag_api_key}"
        self._client = httpx.AsyncClient(
            timeout=config.rag_timeout,
            headers=headers,
            transport=transport,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    async def close(self):
        await self._client.aclose()

    async def query(self, query: str, mode: str = "mix") -> str:
        """LightRAG REST API 쿼리. 실패 또는 빈 응답 시 "" 반환 + WARN 로깅."""
        try:
            resp = await self._client.post(
                f"{self.config.lightrag_url}/query",
                json={"query": query, "mode": mode},
            )
            resp.raise_for_status()
            data = resp.json()
            context = data.get("response", "").strip()
            if not context:
                logger.warning("RAG query returned empty context for: %s", query[:100])
            return context
        except httpx.TimeoutException:
            logger.warning("RAG query timeout for: %s", query[:100])
            return ""
        except httpx.ConnectError:
            logger.warning("RAG service unreachable: %s", self.config.lightrag_url)
            return ""
        except Exception as e:
            logger.warning("RAG query failed: %s", e)
            return ""
