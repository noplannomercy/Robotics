import asyncio
import logging

import httpx

from config import Config

logger = logging.getLogger(__name__)

RETRY_DELAYS = [1, 2]


class LLMClient:
    def __init__(self, config: Config, transport: httpx.AsyncBaseTransport | None = None):
        self.config = config
        self.semaphore = asyncio.Semaphore(config.llm_concurrency)
        headers = {"Content-Type": "application/json"}
        if config.llm_api_key:
            headers["Authorization"] = f"Bearer {config.llm_api_key}"
        self._client = httpx.AsyncClient(
            timeout=config.llm_timeout,
            headers=headers,
            transport=transport,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    async def close(self):
        await self._client.aclose()

    async def generate(self, system: str, user: str, model: str | None = None) -> str:
        payload = {
            "model": model or self.config.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        async with self.semaphore:
            for attempt in range(3):
                try:
                    resp = await self._client.post(self.config.llm_url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    logger.warning("LLM attempt %d failed (transient): %s", attempt + 1, e)
                    if attempt < 2:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                    else:
                        raise
                except httpx.HTTPStatusError as e:
                    if e.response.status_code >= 500 and attempt < 2:
                        logger.warning("LLM attempt %d server error %d", attempt + 1, e.response.status_code)
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                    else:
                        raise
        raise RuntimeError("LLM generate exhausted retries")
