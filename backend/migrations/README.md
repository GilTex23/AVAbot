# Alembic migrations

This project now uses Alembic as the source of truth for database schema changes.

If an existing VPS database was previously created by SQLAlchemy `create_all`, run:

```bash
cd /app/backend
alembic stamp 20260430_0001
alembic upgrade head
```

The container startup script performs this recovery automatically when it sees existing `users` and `subscriptions` tables without an `alembic_version` table.
