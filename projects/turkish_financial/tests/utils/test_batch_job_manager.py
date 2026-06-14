"""
Tests for BatchJobManager and BatchJob
"""
import asyncio
import pytest
from datetime import datetime, timedelta

from utils.batch_job_manager import BatchJob, BatchJobManager, JobStatus


# ---------------------------------------------------------------------------
# BatchJob tests
# ---------------------------------------------------------------------------

def test_batch_job_creation():
    """New job starts with PENDING status and zero progress."""
    mgr = BatchJobManager()
    job = mgr.create_job("kap_batch", {"days_back": 7})

    assert job.status == JobStatus.PENDING
    assert job.progress == 0
    assert job.total == 0
    assert job.result is None
    assert job.error is None
    assert job.started_at is None
    assert job.completed_at is None


def test_batch_job_to_dict():
    """to_dict returns all required keys."""
    mgr = BatchJobManager()
    job = mgr.create_job("kap_batch", {"days_back": 7})
    d = job.to_dict()

    for key in ("job_id", "job_type", "status", "progress", "total",
                "created_at", "started_at", "completed_at", "result", "error"):
        assert key in d, f"Missing key: {key}"

    assert d["status"] == JobStatus.PENDING.value
    assert d["job_type"] == "kap_batch"


# ---------------------------------------------------------------------------
# BatchJobManager – create / get
# ---------------------------------------------------------------------------

def test_create_job_generates_unique_ids():
    mgr = BatchJobManager()
    ids = {mgr.create_job("kap_batch", {}).job_id for _ in range(10)}
    assert len(ids) == 10


def test_get_job_found():
    mgr = BatchJobManager()
    job = mgr.create_job("kap_batch", {})
    found = mgr.get_job(job.job_id)
    assert found is job


def test_get_job_not_found():
    mgr = BatchJobManager()
    assert mgr.get_job("nonexistent-id") is None


# ---------------------------------------------------------------------------
# BatchJobManager – update_job_status
# ---------------------------------------------------------------------------

def test_update_job_status_running():
    mgr = BatchJobManager()
    job = mgr.create_job("kap_batch", {})
    ok = mgr.update_job_status(job.job_id, JobStatus.RUNNING)
    assert ok is True
    assert mgr.get_job(job.job_id).status == JobStatus.RUNNING


def test_update_job_status_completed_with_result():
    mgr = BatchJobManager()
    job = mgr.create_job("kap_batch", {})
    mgr.update_job_status(job.job_id, JobStatus.RUNNING)
    ok = mgr.update_job_status(
        job.job_id, JobStatus.COMPLETED,
        progress=10, total=10,
        result={"scraped": 10}
    )
    assert ok is True
    updated = mgr.get_job(job.job_id)
    assert updated.status == JobStatus.COMPLETED
    assert updated.progress == 10
    assert updated.total == 10
    assert updated.result == {"scraped": 10}
    assert updated.completed_at is not None


def test_update_job_status_failed_with_error():
    mgr = BatchJobManager()
    job = mgr.create_job("kap_batch", {})
    ok = mgr.update_job_status(job.job_id, JobStatus.FAILED, error="timeout")
    assert ok is True
    updated = mgr.get_job(job.job_id)
    assert updated.status == JobStatus.FAILED
    assert updated.error == "timeout"


def test_update_job_status_nonexistent_returns_false():
    mgr = BatchJobManager()
    ok = mgr.update_job_status("bad-id", JobStatus.RUNNING)
    assert ok is False


# ---------------------------------------------------------------------------
# BatchJobManager – cancel_job (new feature)
# ---------------------------------------------------------------------------

def test_cancel_pending_job():
    mgr = BatchJobManager()
    job = mgr.create_job("kap_batch", {})
    result = mgr.cancel_job(job.job_id)
    assert result is True
    assert mgr.get_job(job.job_id).status == JobStatus.CANCELLED


def test_cancel_running_job():
    mgr = BatchJobManager()
    job = mgr.create_job("kap_batch", {})
    mgr.update_job_status(job.job_id, JobStatus.RUNNING)
    result = mgr.cancel_job(job.job_id)
    assert result is True
    assert mgr.get_job(job.job_id).status == JobStatus.CANCELLED


def test_cancel_completed_job_returns_false():
    mgr = BatchJobManager()
    job = mgr.create_job("kap_batch", {})
    mgr.update_job_status(job.job_id, JobStatus.COMPLETED, result={})
    result = mgr.cancel_job(job.job_id)
    assert result is False
    assert mgr.get_job(job.job_id).status == JobStatus.COMPLETED


def test_cancel_nonexistent_job_returns_false():
    mgr = BatchJobManager()
    assert mgr.cancel_job("does-not-exist") is False


def test_cancelled_job_sets_completed_at():
    mgr = BatchJobManager()
    job = mgr.create_job("kap_batch", {})
    before = datetime.now()
    mgr.cancel_job(job.job_id)
    after = datetime.now()
    completed_at = mgr.get_job(job.job_id).completed_at
    assert completed_at is not None
    assert before <= completed_at <= after


# ---------------------------------------------------------------------------
# BatchJobManager – list_jobs
# ---------------------------------------------------------------------------

def test_list_jobs_all():
    mgr = BatchJobManager()
    for _ in range(3):
        mgr.create_job("kap_batch", {})
    assert len(mgr.list_jobs()) == 3


def test_list_jobs_filter_by_status():
    mgr = BatchJobManager()
    j1 = mgr.create_job("kap_batch", {})
    j2 = mgr.create_job("kap_batch", {})
    mgr.create_job("bist_batch", {})

    mgr.cancel_job(j1.job_id)
    mgr.cancel_job(j2.job_id)

    cancelled = mgr.list_jobs(status=JobStatus.CANCELLED)
    assert len(cancelled) == 2

    pending = mgr.list_jobs(status=JobStatus.PENDING)
    assert len(pending) == 1


def test_list_jobs_filter_by_type():
    mgr = BatchJobManager()
    mgr.create_job("kap_batch", {})
    mgr.create_job("kap_batch", {})
    mgr.create_job("bist_batch", {})

    kap_jobs = mgr.list_jobs(job_type="kap_batch")
    assert len(kap_jobs) == 2

    bist_jobs = mgr.list_jobs(job_type="bist_batch")
    assert len(bist_jobs) == 1


def test_list_jobs_limit():
    mgr = BatchJobManager()
    for _ in range(10):
        mgr.create_job("kap_batch", {})
    assert len(mgr.list_jobs(limit=5)) == 5


# ---------------------------------------------------------------------------
# BatchJobManager – get_stats (new feature)
# ---------------------------------------------------------------------------

def test_get_stats_empty():
    mgr = BatchJobManager()
    stats = mgr.get_stats()
    for status in JobStatus:
        assert stats[status.value] == 0


def test_get_stats_counts():
    mgr = BatchJobManager()
    j1 = mgr.create_job("kap_batch", {})
    j2 = mgr.create_job("kap_batch", {})
    j3 = mgr.create_job("kap_batch", {})

    mgr.update_job_status(j1.job_id, JobStatus.COMPLETED, result={})
    mgr.update_job_status(j2.job_id, JobStatus.FAILED, error="err")

    stats = mgr.get_stats()
    assert stats["pending"] == 1
    assert stats["completed"] == 1
    assert stats["failed"] == 1
    assert stats["running"] == 0
    assert stats["cancelled"] == 0


# ---------------------------------------------------------------------------
# BatchJobManager – cleanup_old_jobs
# ---------------------------------------------------------------------------

def test_cleanup_old_jobs():
    mgr = BatchJobManager()
    job = mgr.create_job("kap_batch", {})
    mgr.update_job_status(job.job_id, JobStatus.COMPLETED, result={})
    # Manually age the job
    mgr.jobs[job.job_id].completed_at = datetime.now() - timedelta(hours=25)

    removed = mgr.cleanup_old_jobs(max_age_hours=24)
    assert removed == 1
    assert mgr.get_job(job.job_id) is None


def test_cleanup_leaves_recent_jobs():
    mgr = BatchJobManager()
    job = mgr.create_job("kap_batch", {})
    mgr.update_job_status(job.job_id, JobStatus.COMPLETED, result={})

    removed = mgr.cleanup_old_jobs(max_age_hours=24)
    assert removed == 0
    assert mgr.get_job(job.job_id) is not None


# ---------------------------------------------------------------------------
# BatchJobManager – run_job (async)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_job_success():
    mgr = BatchJobManager()
    job = mgr.create_job("kap_batch", {})

    async def task():
        return {"scraped": 5}

    await mgr.run_job_async(job.job_id, task)
    updated = mgr.get_job(job.job_id)
    assert updated.status == JobStatus.COMPLETED
    assert updated.result == {"scraped": 5}


@pytest.mark.asyncio
async def test_run_job_failure():
    mgr = BatchJobManager()
    job = mgr.create_job("kap_batch", {})

    async def failing_task():
        raise RuntimeError("network error")

    await mgr.run_job_async(job.job_id, failing_task)
    updated = mgr.get_job(job.job_id)
    assert updated.status == JobStatus.FAILED
    assert "network error" in updated.error
