import hashlib
import os
from pathlib import Path

import mysql.connector


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"


def split_statements(script: str) -> list[str]:
    return [statement.strip() for statement in script.split(";") if statement.strip()]


def connect():
    return mysql.connector.connect(
        host=os.environ["RDS_HOST"],
        user=os.environ["DB_USER"],
        password=os.environ["RDS_PASSWORD"],
        database=os.environ["DB_NAME"],
    )


def migrate() -> None:
    connection = connect()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(255) PRIMARY KEY,
                checksum CHAR(64) NOT NULL,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        connection.commit()

        cursor.execute("SELECT version, checksum FROM schema_migrations")
        applied = {row["version"]: row["checksum"] for row in cursor.fetchall()}

        for migration in sorted(MIGRATIONS.glob("*.sql")):
            script = migration.read_text(encoding="utf-8")
            checksum = hashlib.sha256(script.encode("utf-8")).hexdigest()
            if migration.name in applied:
                if applied[migration.name] != checksum:
                    raise RuntimeError(
                        f"Applied migration changed: {migration.name}. Create a new migration instead."
                    )
                continue

            for statement in split_statements(script):
                cursor.execute(statement)
            cursor.execute(
                "INSERT INTO schema_migrations(version, checksum) VALUES (%s, %s)",
                (migration.name, checksum),
            )
            connection.commit()
            print(f"Applied migration {migration.name}", flush=True)
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    migrate()
