import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from repositories.job_repository import recover_expired_leases, retry_delay_seconds
from services.background_worker import (
    REMINDER_SCAN_JOB,
    process_due_job,
    reminder_scan_key,
)


class FakeQueue:
    def __init__(self, job_id=None):
        self.job_id = job_id
        self.scheduled = []

    def pop_due(self, _now):
        value, self.job_id = self.job_id, None
        return value

    def schedule(self, job_id, run_at):
        self.scheduled.append((job_id, run_at))


class BackgroundWorkerTests(unittest.TestCase):
    def test_reminder_scan_key_is_stable_inside_interval(self):
        first = datetime(2026, 9, 6, 10, 1, 1)
        second = datetime(2026, 9, 6, 10, 4, 59)

        self.assertEqual(reminder_scan_key(first, 300), reminder_scan_key(second, 300))
        self.assertNotEqual(
            reminder_scan_key(first, 300),
            reminder_scan_key(datetime(2026, 9, 6, 10, 5, 0), 300),
        )

    def test_retry_backoff_is_exponential_and_capped(self):
        self.assertEqual(10, retry_delay_seconds(1, 10, 900))
        self.assertEqual(40, retry_delay_seconds(3, 10, 900))
        self.assertEqual(900, retry_delay_seconds(20, 10, 900))

    def test_expired_processing_lease_returns_to_retry_queue(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.rowcount = 1
        now = datetime(2026, 9, 6, 10, 0, 0)

        recovered = recover_expired_leases(connection, now)

        self.assertEqual(1, recovered)
        self.assertIn("status = 'retrying'", cursor.execute.call_args.args[0])
        connection.commit.assert_called_once()

    @patch("services.background_worker.job_repository.complete_job")
    @patch("services.background_worker.reminder_repository.scan_operational_reminders")
    @patch("services.background_worker.job_repository.claim_job")
    def test_due_reminder_job_completes(self, claim_job, scan, complete_job):
        now = datetime(2026, 9, 6, 10, 0, 0)
        connection = MagicMock()
        queue = FakeQueue(job_id=7)
        claim_job.return_value = {"id": 7, "event_type": REMINDER_SCAN_JOB, "attempts": 1}
        complete_job.return_value = {"id": 7, "status": "completed"}

        result = process_due_job(connection, queue, now)

        claim_job.assert_called_once_with(connection, 7, now + timedelta(seconds=60))
        scan.assert_called_once_with(connection, None, now)
        complete_job.assert_called_once_with(connection, 7, now)
        self.assertEqual("completed", result["status"])

    @patch.dict("os.environ", {"WORKER_MAX_ATTEMPTS": "5", "WORKER_RETRY_BASE_SECONDS": "10", "WORKER_RETRY_MAX_SECONDS": "900"})
    @patch("services.background_worker.job_repository.fail_job")
    @patch("services.background_worker.reminder_repository.scan_operational_reminders")
    @patch("services.background_worker.job_repository.claim_job")
    def test_failed_job_is_rescheduled(self, claim_job, scan, fail_job):
        now = datetime(2026, 9, 6, 10, 0, 0)
        retry_at = now + timedelta(seconds=10)
        queue = FakeQueue(job_id=8)
        claim_job.return_value = {"id": 8, "event_type": REMINDER_SCAN_JOB, "attempts": 1}
        scan.side_effect = RuntimeError("database unavailable")
        fail_job.return_value = {"id": 8, "status": "retrying", "next_attempt_at": retry_at}

        result = process_due_job(MagicMock(), queue, now)

        self.assertEqual("retrying", result["status"])
        self.assertEqual([(8, retry_at)], queue.scheduled)


if __name__ == "__main__":
    unittest.main()
