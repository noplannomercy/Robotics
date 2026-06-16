# observation.py
"""적재 결과 현상 요약. 정성 판단(빈약 지점 등)은 수동 관찰(docs/observations) 몫."""
from dataclasses import dataclass

from ingest_driver import IngestionReport


@dataclass(frozen=True)
class Observation:
    total: int
    completed: int
    failed: int
    skipped: int

    @property
    def pass_rate(self) -> float:
        return self.completed / self.total if self.total else 0.0


def summarize(report: IngestionReport) -> Observation:
    completed = len(report.completed)
    failed = len(report.failed)
    skipped = len(report.skipped_missing)
    return Observation(
        total=completed + failed + skipped,
        completed=completed,
        failed=failed,
        skipped=skipped,
    )
