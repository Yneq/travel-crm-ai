import os
import sys
import time
from pathlib import Path

import redis


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dependencies import get_db
from services.background_worker import (
    ensure_reminder_scan_job,
    process_due_job,
    recover_jobs,
    utc_now,
)
from services.job_queue import RedisJobQueue


def run() -> None:
    poll_seconds = float(os.getenv("WORKER_POLL_SECONDS", "2"))
    scan_interval = int(os.getenv("REMINDER_SCAN_INTERVAL_SECONDS", "300"))
    client = redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        decode_responses=True,
    )
    queue = RedisJobQueue(client)
    print("VoyageOps worker started", flush=True)
    while True:
        connection = None
        try:
            connection = get_db()
            now = utc_now()
            ensure_reminder_scan_job(connection, queue, now, scan_interval)
            recover_jobs(connection, queue, now)
            while process_due_job(connection, queue, now) is not None:
                now = utc_now()
        except Exception as exc:
            print(f"Worker tick failed: {type(exc).__name__}: {exc}", flush=True)
        finally:
            if connection is not None:
                connection.close()
        time.sleep(poll_seconds)


if __name__ == "__main__":
    run()
