# callback.py
import asyncio
import json
import logging
from typing import Sequence

import httpx

logger = logging.getLogger(__name__)

RETRIES = 3
DELAYS = [1, 2, 4]


def _apply_field_map(payload: dict, field_map_json: str, keep_unmapped: bool) -> dict:
    """Forge CALLBACK_FIELD_MAP과 동일 로직: 필드명 rename + 불필요 필드 제거."""
    if not field_map_json:
        return payload
    try:
        rename_map: dict[str, str] = json.loads(field_map_json)
    except json.JSONDecodeError:
        logger.error("CALLBACK_FIELD_MAP JSON 파싱 실패: %s", field_map_json)
        return payload
    result: dict = {}
    for k, v in payload.items():
        new_key = rename_map.get(k, k)
        if not keep_unmapped and k not in rename_map:
            continue
        result[new_key] = v
    return result


async def send_callback(
    url: str | None,
    payload: dict,
    api_key: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    delays: Sequence[float] | None = None,
    field_map: str = "",
    keep_unmapped: bool = True,
) -> None:
    """완료 콜백 전송. 실패 시 3회 retry, 최종 실패는 로그만."""
    if not url:
        return

    payload = _apply_field_map(payload, field_map, keep_unmapped)

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
