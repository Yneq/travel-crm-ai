from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user, get_db_connection, get_redis_connection, require_roles
from models.job import IntegrationStatusResponse, JobResponse, WorkerStatusResponse
from repositories import job_repository
from services.job_queue import RedisJobQueue
from services.integration_readiness import integration_status


router = APIRouter(prefix="/api/operations", tags=["background operations"])
admin_access = require_roles("admin")


@router.get("/jobs", response_model=list[JobResponse])
def list_jobs(
    limit: int = 50,
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(get_current_user),
):
    return job_repository.list_jobs(connection, min(max(limit, 1), 100))


@router.get("/worker/status", response_model=WorkerStatusResponse)
def worker_status(
    connection=Depends(get_db_connection),
    redis_client=Depends(get_redis_connection),
    _current_user: dict = Depends(get_current_user),
):
    counts = job_repository.status_counts(connection)
    try:
        redis_ready = RedisJobQueue(redis_client).ping()
    except Exception:
        redis_ready = False
    return {
        "redis_ready": redis_ready,
        "scheduled": counts.get("scheduled", 0),
        "processing": counts.get("processing", 0),
        "retrying": counts.get("retrying", 0),
        "completed": counts.get("completed", 0),
        "dead_letter": counts.get("dead_letter", 0),
    }


@router.get("/integrations/status", response_model=IntegrationStatusResponse)
def integrations_status(
    _current_user: dict = Depends(get_current_user),
):
    return integration_status()


@router.post("/jobs/{job_id}/retry", response_model=JobResponse)
def retry_dead_letter_job(
    job_id: int,
    connection=Depends(get_db_connection),
    redis_client=Depends(get_redis_connection),
    _current_user: dict = Depends(admin_access),
):
    current = job_repository.get_job(connection, job_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Background job not found")
    if current["status"] != "dead_letter":
        raise HTTPException(status_code=409, detail="Only a dead-letter job can be retried manually")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    job = job_repository.retry_dead_letter(connection, job_id, now)
    RedisJobQueue(redis_client).schedule(job_id, now)
    return job
