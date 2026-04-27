# callback.py
import asyncio
import logging
from typing import Sequence

import httpx

logger = logging.getLogger(__name__)

RETRIES = 3
DELAYS = [1, 2, 4]


async def send_callback(
    url: str | None,
    payload: dict,
    api_key: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    delays: Sequence[float] | None = None,
) -> None:
    """ingestion-router로 완료 콜백 전송. 실패 시 3회 retry, 최종 실패는 로그만."""
    if not url:
        return

    retry_delays = delays if delays is not None else DELAYS

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    client_kwargs: dict = {"timeout": 30, "headers": headers}
    if transport:
        client_kwargs["transport"] = transport

    async with httpx.AsyncClient(**client_kwargs) as client:
        for attempt in range(RETRIES):
            try:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                logger.info("Callback sent to %s (status %d)", url, resp.status_code)
                return
            except Exception as e:
                logger.warning("Callback attempt %d/%d failed: %s", attempt + 1, RETRIES, e)
                if attempt < RETRIES - 1:
                    await asyncio.sleep(retry_delays[attempt])
    logger.error("Callback failed after %d attempts: %s", RETRIES, url)
