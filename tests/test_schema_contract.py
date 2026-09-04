import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SchemaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.migration = "\n".join(
            migration.read_text()
            for migration in sorted((ROOT / "migrations").glob("*.sql"))
        )
        cls.tables = set(
            re.findall(
                r"CREATE TABLE(?: IF NOT EXISTS)?\s+(\w+)",
                cls.migration,
                flags=re.IGNORECASE,
            )
        )

    def test_operational_tables_exist(self):
        expected = {
            "roles",
            "staff_users",
            "members",
            "member_preferences",
            "travel_requests",
            "trips",
            "trip_items",
            "quotes",
            "quote_items",
            "orders",
            "payments",
            "documents",
            "tasks",
            "reminders",
            "ai_runs",
            "integration_events",
            "audit_logs",
        }

        self.assertTrue(expected.issubset(self.tables))

    def test_payment_and_integration_idempotency_are_explicit(self):
        self.assertGreaterEqual(self.migration.count("idempotency_key"), 3)
        self.assertIn("UNIQUE", self.migration)
        self.assertIn("uk_orders_quote", self.migration)
        self.assertIn("attempt_number", self.migration)

    def test_ai_runs_require_review_and_idempotency_metadata(self):
        self.assertIn("uk_ai_runs_idempotency", self.migration)
        self.assertIn("reviewed_by", self.migration)
        self.assertIn("applied_trip_id", self.migration)

    def test_operational_reminders_are_deduplicated_and_reviewable(self):
        self.assertIn("uk_reminders_dedup", self.migration)
        self.assertIn("reminder_type", self.migration)
        self.assertIn("reviewed_by", self.migration)
        self.assertIn("reviewed_at", self.migration)


if __name__ == "__main__":
    unittest.main()
