from ingest_driver import IngestionReport
from observation import summarize, Observation


def test_summarize_counts_and_pass_rate():
    report = IngestionReport(
        completed=["A", "B", "C"],
        failed=[("D", "failed")],
        skipped_missing=["E"],
    )
    obs = summarize(report)
    assert obs == Observation(total=5, completed=3, failed=1, skipped=1)
    assert obs.pass_rate == 0.6  # 3/5


def test_pass_rate_zero_when_empty():
    obs = summarize(IngestionReport())
    assert obs.total == 0
    assert obs.pass_rate == 0.0
