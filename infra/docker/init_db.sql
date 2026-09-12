-- Runs once, when the pgdata volume is first created. Postgres ignores this
-- file on every subsequent start, so adding to it later requires a
-- `docker compose down -v` to take effect. Announce that before changing it.
--
-- Only extensions belong here. Tables are owned by Alembic
-- (backend/db/migrations) so that local, CI and RDS all get their schema from
-- exactly one place.

-- pgvector: the embedding column on regulation_chunks.
CREATE EXTENSION IF NOT EXISTS vector;

-- pg_trgm: fuzzy matching on plant and document names.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- gen_random_uuid(), used for job_runs primary keys.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
