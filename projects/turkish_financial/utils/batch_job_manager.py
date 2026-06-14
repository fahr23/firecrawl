"""
Batch job management for async scraping operations
"""
import logging
import asyncio
import uuid
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Job status enumeration"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BatchJob:
    """Represents a batch scraping job"""
    
    def __init__(
        self,
        job_id: str,
        job_type: str,
        params: Dict[str, Any]
    ):
        self.job_id = job_id
        self.job_type = job_type
        self.params = params
        self.status = JobStatus.PENDING
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.progress = 0
        self.total = 0
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary"""
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status.value,
            "progress": self.progress,
            "total": self.total,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error
        }


class BatchJobManager:
    """Manages batch scraping jobs"""
    
    def __init__(self):
        """Initialize job manager"""
        self.jobs: Dict[str, BatchJob] = {}
        self._cleanup_interval = 3600  # 1 hour
    
    def create_job(
        self,
        job_type: str,
        params: Dict[str, Any]
    ) -> BatchJob:
        """
        Create a new batch job
        
        Args:
            job_type: Type of job (kap_batch, bist_batch, etc.)
            params: Job parameters
            
        Returns:
            BatchJob instance
        """
        job_id = str(uuid.uuid4())
        job = BatchJob(job_id, job_type, params)
        self.jobs[job_id] = job
        logger.info(f"Created batch job {job_id} of type {job_type}")
        return job
    
    def get_job(self, job_id: str) -> Optional[BatchJob]:
        """Get job by ID"""
        return self.jobs.get(job_id)
    
    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: Optional[int] = None,
        total: Optional[int] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> bool:
        """
        Update job status
        
        Args:
            job_id: Job ID
            status: New status
            progress: Current progress
            total: Total items
            result: Job result
            error: Error message
            
        Returns:
            Success status
        """
        job = self.jobs.get(job_id)
        if not job:
            logger.warning(f"Job {job_id} not found")
            return False
        
        job.status = status
        
        if status == JobStatus.RUNNING and not job.started_at:
            job.started_at = datetime.now()
        
        if status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            job.completed_at = datetime.now()
        
        if progress is not None:
            job.progress = progress
        
        if total is not None:
            job.total = total
        
        if result is not None:
            job.result = result
        
        if error is not None:
            job.error = error
        
        logger.debug(f"Updated job {job_id} status to {status.value}")
        return True
    
    async def run_job_async(
        self,
        job_id: str,
        task_func: Callable,
        *args,
        **kwargs
    ) -> None:
        """
        Run a job asynchronously
        
        Args:
            job_id: Job ID
            task_func: Async function to execute
            *args: Positional arguments for task_func
            **kwargs: Keyword arguments for task_func
        """
        job = self.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return
        
        self.update_job_status(job_id, JobStatus.RUNNING)
        
        try:
            result = await task_func(*args, **kwargs)
            self.update_job_status(
                job_id,
                JobStatus.COMPLETED,
                progress=job.total if job.total > 0 else 1,
                total=job.total if job.total > 0 else 1,
                result=result
            )
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}", exc_info=True)
            self.update_job_status(
                job_id,
                JobStatus.FAILED,
                error=str(e)
            )
    
    def cleanup_old_jobs(self, max_age_hours: int = 24) -> int:
        """
        Remove old completed/failed jobs
        
        Args:
            max_age_hours: Maximum age in hours
            
        Returns:
            Number of jobs removed
        """
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        removed = 0
        
        for job_id, job in list(self.jobs.items()):
            if job.completed_at and job.completed_at < cutoff:
                del self.jobs[job_id]
                removed += 1
        
        if removed > 0:
            logger.info(f"Cleaned up {removed} old jobs")
        
        return removed
    
    def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        job_type: Optional[str] = None,
        limit: int = 100
    ) -> List[BatchJob]:
        """
        List jobs with optional filters
        
        Args:
            status: Filter by status
            job_type: Filter by job type
            limit: Maximum results
            
        Returns:
            List of jobs
        """
        jobs = list(self.jobs.values())
        
        if status:
            jobs = [j for j in jobs if j.status == status]
        
        if job_type:
            jobs = [j for j in jobs if j.job_type == job_type]
        
        # Sort by created_at descending
        jobs.sort(key=lambda x: x.created_at, reverse=True)
        
        return jobs[:limit]

    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a pending or running job

        Args:
            job_id: Job ID to cancel

        Returns:
            True if cancelled successfully, False if not found or already terminal
        """
        job = self.jobs.get(job_id)
        if not job:
            logger.warning(f"Job {job_id} not found")
            return False

        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            logger.warning(f"Job {job_id} is already in terminal state: {job.status}")
            return False

        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now()
        logger.info(f"Cancelled job {job_id}")
        return True

    def get_stats(self) -> Dict[str, int]:
        """
        Return job counts grouped by status

        Returns:
            Dict mapping status name to count
        """
        stats: Dict[str, int] = {s.value: 0 for s in JobStatus}
        for job in self.jobs.values():
            stats[job.status.value] += 1
        return stats


# Global job manager instance
job_manager = BatchJobManager()
