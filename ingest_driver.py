# ingest_driver.py
"""의존성 순서대로 패키지를 Robotics에 순차 투입하는 드라이버.

run_ingestion: 순수 오케스트레이션(클라이언트 주입). 단위 테스트 대상.
HttpRoboticsClient: 실제 /jobs 호출. 사내망 통합 시 사용(단위 테스트 제외).
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

logger = logging.getLogger(__name__)


class RoboticsClient(Protocol):
    def submit(self, name: str, source: bytes, asset_type: str) -> str: ...
    def wait_until_done(self, job_id: str) -> str: ...


@dataclass
class IngestionReport:
    completed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    skipped_missing: list[str] = field(default_factory=list)


def run_ingestion(
    ordered: list[str],
    client: RoboticsClient,
    source_resolver: Callable[[str], bytes | None],
    asset_type: str = "plsql",
) -> IngestionReport:
    """ordered 순서대로: 소스 조회 → submit → 완료 대기 → 다음.
    완료 대기로 callee가 다음 패키지 처리 전에 LightRAG에 적재됨을 보장한다."""
    report = IngestionReport()
    for name in ordered:
        source = source_resolver(name)
        if source is None:
            report.skipped_missing.append(name)
            continue
        job_id = client.submit(name, source, asset_type)
        status = client.wait_until_done(job_id)
        if status == "completed":
            report.completed.append(name)
        else:
            report.failed.append((name, status))
    return report


class HttpRoboticsClient:
    """실제 Robotics /jobs 호출. (사내망 통합용 — 단위 테스트 대상 아님)"""

    def __init__(self, base_url: str, poll_interval: float = 2.0, timeout: float = 600.0):
        import httpx
        self._http = httpx.Client(base_url=base_url, timeout=30.0)
        self._poll = poll_interval
        self._timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def submit(self, name: str, source: bytes, asset_type: str) -> str:
        resp = self._http.post(
            "/jobs",
            files={"file": (name, source)},
            data={"asset_type": asset_type, "requested_by": "ingest_driver"},
        )
        resp.raise_for_status()
        return resp.json()["job_id"]

    def wait_until_done(self, job_id: str) -> str:
        import httpx
        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            try:
                resp = self._http.get(f"/jobs/{job_id}")
                resp.raise_for_status()
                status = resp.json()["status"]
                if status in ("completed", "failed"):
                    return status
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                logger.warning("폴링 중 일시적 오류 (job=%s): %s — 재시도 중", job_id, exc)
            time.sleep(self._poll)
        return "timeout"

    def close(self) -> None:
        self._http.close()
