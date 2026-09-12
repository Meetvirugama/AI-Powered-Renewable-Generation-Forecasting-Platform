"""add pgvector embedding columns to regulation_chunks

Adds the vector storage the RAG copilot needs:
  - the `vector` extension
  - embedding VECTOR(1024)   (bge-m3 dense output)
  - embed_model              (guards against a corpus/query model mismatch)
  - chunk_id UNIQUE          (idempotent re-ingest)
  - an HNSW cosine index

Note on the index: HNSW is used rather than ivfflat deliberately. ivfflat
clusters on whatever rows exist when the index is built, so creating it on an
empty table (as a migration necessarily does) destroys recall with no error.
HNSW builds incrementally and is safe to create ahead of the data.

Revision ID: a1f4c9e27b30
Revises: 10bcd26b623c
Create Date: 2026-09-12 09:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1f4c9e27b30'
down_revision: Union[str, None] = '10bcd26b623c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1024


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == 'postgresql'


def upgrade() -> None:
    if _is_postgres():
        op.execute('CREATE EXTENSION IF NOT EXISTS vector')
        from pgvector.sqlalchemy import Vector
        embedding_type = Vector(EMBEDDING_DIM)
    else:
        embedding_type = sa.Text()

    op.add_column('regulation_chunks', sa.Column('chunk_id', sa.String(), nullable=True))
    op.add_column('regulation_chunks', sa.Column('embedding', embedding_type, nullable=True))
    op.add_column('regulation_chunks', sa.Column('embed_model', sa.String(), nullable=True))

    # Unique index, not a unique constraint: SQLite cannot ALTER a constraint
    # into an existing table, and the index enforces the same invariant.
    op.create_index('uq_regulation_chunks_chunk_id', 'regulation_chunks', ['chunk_id'], unique=True)
    op.create_index('ix_regulation_chunks_doc', 'regulation_chunks', ['doc_name'])

    if _is_postgres():
        op.execute(
            'CREATE INDEX IF NOT EXISTS ix_regulation_chunks_embedding_hnsw '
            'ON regulation_chunks USING hnsw (embedding vector_cosine_ops) '
            'WITH (m = 16, ef_construction = 64)'
        )
        # Sparse half of hybrid retrieval; BM25 itself is in-process, but this
        # keeps a SQL-side keyword fallback available.
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_regulation_chunks_fts "
            "ON regulation_chunks USING gin (to_tsvector('english', chunk_text))"
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute('DROP INDEX IF EXISTS ix_regulation_chunks_fts')
        op.execute('DROP INDEX IF EXISTS ix_regulation_chunks_embedding_hnsw')

    op.drop_index('ix_regulation_chunks_doc', table_name='regulation_chunks')
    op.drop_index('uq_regulation_chunks_chunk_id', table_name='regulation_chunks')

    op.drop_column('regulation_chunks', 'embed_model')
    op.drop_column('regulation_chunks', 'embedding')
    op.drop_column('regulation_chunks', 'chunk_id')
