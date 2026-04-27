from datetime import datetime, timezone
import pytest
from models import AssetType, Job, JobStatus


def test_job_status_values():
    assert JobStatus.QUEUED == "queued"
    assert JobStatus.PROCESSING == "processing"
    assert JobStatus.COMPLETED == "completed"
    assert JobStatus.FAILED == "failed"


def test_asset_type_values():
    assert AssetType.PLSQL == "plsql"
    assert AssetType.DICTIONARY == "dictionary"
    assert AssetType.ERD == "erd"
    assert AssetType.POLICY == "policy"


def test_job_creation():
    job = Job(
        id="test-id",
        status=JobStatus.QUEUED,
        asset_type=AssetType.PLSQL,
        file_name="PKG_TEST.sql",
        source_hash="abc123",
    )
    assert job.id == "test-id"
    assert job.status == JobStatus.QUEUED
    assert job.result is None
    assert job.error is None
    assert job.attempts == 0
    assert isinstance(job.created_at, datetime)


def test_job_optional_fields():
    job = Job(
        id="x",
        status=JobStatus.COMPLETED,
        asset_type="plsql",
        file_name="f.sql",
        source_hash="h",
        result="# 역문서",
        callback_url="http://router/callback",
        requested_by="ingestion-router",
    )
    assert job.result == "# 역문서"
    assert job.callback_url == "http://router/callback"
