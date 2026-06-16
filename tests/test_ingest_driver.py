from ingest_driver import run_ingestion, IngestionReport


class FakeClient:
    """submit/wait 호출 순서를 기록하는 가짜 클라이언트.
    각 submit 직후 반드시 wait가 와야 함(순차성)을 검증한다."""
    def __init__(self, fail: set[str] | None = None):
        self.fail = fail or set()
        self.events: list[str] = []
        self._pending: str | None = None

    def submit(self, name: str, source: bytes, asset_type: str) -> str:
        assert self._pending is None, f"이전 작업({self._pending}) 미완료 상태에서 {name} 제출됨"
        self._pending = name
        self.events.append(f"submit:{name}")
        return f"job-{name}"

    def wait_until_done(self, job_id: str) -> str:
        name = job_id.removeprefix("job-")
        assert self._pending == name
        self._pending = None
        self.events.append(f"wait:{name}")
        return "failed" if name in self.fail else "completed"


def _sources(available):
    return lambda name: (b"SRC:" + name.encode()) if name in available else None


def test_submits_in_given_order_and_waits_each():
    client = FakeClient()
    ordered = ["C", "B", "A"]
    report = run_ingestion(ordered, client, _sources({"A", "B", "C"}))
    assert client.events == [
        "submit:C", "wait:C", "submit:B", "wait:B", "submit:A", "wait:A",
    ]
    assert report.completed == ["C", "B", "A"]
    assert report.failed == []
    assert report.skipped_missing == []


def test_missing_source_skipped():
    client = FakeClient()
    report = run_ingestion(["A", "B"], client, _sources({"A"}))
    assert report.skipped_missing == ["B"]
    assert report.completed == ["A"]
    assert client.events == ["submit:A", "wait:A"]


def test_failed_status_recorded():
    client = FakeClient(fail={"B"})
    report = run_ingestion(["A", "B"], client, _sources({"A", "B"}))
    assert report.completed == ["A"]
    assert report.failed == [("B", "failed")]
