import os
import re
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path("/app/database/migrations")

DATABASE_URL = os.environ["DATABASE_URL"].replace(
    "postgresql+psycopg://",
    "postgresql://",
)

PATTERN = re.compile(r"^\d{3}_[a-z0-9_]+\.sql$")


def main():
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(100) PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if not PATTERN.match(migration.name):
                continue

            applied = connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version = %s",
                (migration.name,),
            ).fetchone()

            if applied:
                print(f"Ya aplicada: {migration.name}")
                continue

            sql = migration.read_text(encoding="utf-8")

            with connection.transaction():
                connection.execute(sql)
                connection.execute(
                    """
                    INSERT INTO schema_migrations (version)
                    VALUES (%s)
                    """,
                    (migration.name,),
                )

            print(f"Aplicada: {migration.name}")

    print("Migraciones verificadas correctamente.")


if __name__ == "__main__":
    main()
