import hashlib
import os
import re
from pathlib import Path

import psycopg

def resolve_migrations_dir():
    configured = os.environ.get("MIGRATIONS_DIR")

    if configured:
        directory = Path(configured).resolve()
        if not directory.is_dir():
            raise RuntimeError(f"MIGRATIONS_DIR no existe: {directory}")
        return directory

    script = Path(__file__).resolve()

    candidates = [
        script.parents[2] / "database" / "migrations",
        script.parents[1] / "database" / "migrations",
        script.parent / "migrations",
    ]

    for directory in candidates:
        if directory.is_dir() and any(directory.glob("*.sql")):
            return directory

    raise RuntimeError("No se encontró el directorio de migraciones")


MIGRATIONS_DIR = resolve_migrations_dir()

DATABASE_URL = os.environ["DATABASE_URL"].replace(
    "postgresql+psycopg://",
    "postgresql://",
)

PATTERN = re.compile(r"^\d{3}_[a-z0-9_]+\.sql$")


def main():
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("SELECT pg_advisory_lock(48002, 1)")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(100) PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        connection.execute("ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum VARCHAR(64)")

        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if not PATTERN.match(migration.name):
                continue

            sql = migration.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            applied = connection.execute(
                "SELECT checksum FROM schema_migrations WHERE version = %s",
                (migration.name,),
            ).fetchone()

            if applied:
                if applied[0] and applied[0] != checksum:
                    raise RuntimeError(f"Migración aplicada modificada: {migration.name}")
                if applied[0] is None:
                    connection.execute("UPDATE schema_migrations SET checksum = %s WHERE version = %s", (checksum, migration.name))
                print(f"Ya aplicada: {migration.name}")
                continue

            # Legacy 013 wrapped itself in BEGIN/COMMIT. The runner owns the
            # transaction so schema changes and the ledger commit atomically.
            if migration.name == "013_conversation_archiving.sql":
                sql = re.sub(r"(?im)^\s*(?:BEGIN|COMMIT);\s*$", "", sql)

            with connection.transaction():
                connection.execute(sql)
                connection.execute(
                    """
                    INSERT INTO schema_migrations (version, checksum)
                    VALUES (%s, %s)
                    """,
                    (migration.name, checksum),
                )

            print(f"Aplicada: {migration.name}")

    print("Migraciones verificadas correctamente.")


if __name__ == "__main__":
    main()
