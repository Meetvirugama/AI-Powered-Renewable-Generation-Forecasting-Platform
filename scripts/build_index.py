#!/usr/bin/env python
"""Build the regulation vector index: PDFs -> chunks -> embeddings -> Postgres.

Run offline, not in a request path. On a Colab T4 the embedding step for a
~2000-chunk corpus takes well under a minute; on a laptop CPU expect 10-20.

    # local stack
    python scripts/build_index.py

    # against RDS, through an SSM port-forward
    DATABASE_URL=postgresql+psycopg2://... python scripts/build_index.py

    # dry run: chunk and report, write nothing
    python scripts/build_index.py --dry-run

Two things this script is careful about, both of which silently destroy
retrieval quality rather than failing:

1. The ANN index is created *after* the rows are inserted. An ivfflat index
   built on an empty table clusters on nothing and recall collapses with no
   error. (The Alembic migration uses HNSW, which is safe to create empty, but
   the ordering here is correct for either.)
2. Every row records the model that embedded it. Embedding the corpus with one
   model and querying with another returns plausible neighbours that are
   meaningless, and nothing anywhere raises.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter
from pathlib import Path

# Make `backend` importable when run as a plain script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text as sql  # noqa: E402

from backend.modules.rag import embed, ingest  # noqa: E402

logger = logging.getLogger("build_index")

BATCH = 64


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--regulations", type=Path, default=Path("regulations"))
    p.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    p.add_argument("--dry-run", action="store_true", help="chunk and report, write nothing")
    p.add_argument("--truncate", action="store_true", help="clear the table before inserting")
    p.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="write chunks with a NULL embedding; retrieval stays BM25-only",
    )
    p.add_argument("--jsonl", type=Path, default=None, help="also write chunks to this JSONL file")
    return p.parse_args()


def report(chunks: list[ingest.Chunk]) -> bool:
    """Print the chunker sanity check. Returns False if the corpus looks wrong.

    Twenty minutes here is worth more than any amount of prompt tuning later:
    embedding a badly chunked corpus produces a copilot that cites confidently
    and wrongly, and no amount of downstream work recovers it.
    """
    if not chunks:
        logger.error("no chunks produced")
        return False

    by_doc = Counter(c.doc_name for c in chunks)
    unmatched = sum(1 for c in chunks if c.clause == ingest.PREAMBLE)
    lengths = sorted(len(c.chunk_text) for c in chunks)

    print(f"\ntotal chunks : {len(chunks)}")
    print(f"median chars : {lengths[len(lengths) // 2]}")
    print(f"unmatched    : {unmatched} ({unmatched / len(chunks):.0%}) with no clause heading")
    print("by document  :")
    for name, count in by_doc.most_common():
        print(f"  {count:5d}  {name}")

    # The test that actually matters: can the corpus answer the demo question?
    hits = [
        c for c in chunks
        if "deviation" in c.chunk_text.lower() and "charge" in c.chunk_text.lower()
    ]
    print(f"\ndeviation-charge chunks: {len(hits)}")
    for h in hits[:3]:
        print(f"  {h.doc_name} | {h.clause} | p.{h.page_no}")
        print(f"    {h.chunk_text[:160]}...")

    ok = True
    if unmatched / len(chunks) > 0.30:
        logger.warning(
            "%.0f%% of chunks matched no clause heading. The PDF probably uses a "
            "numbering style CLAUSE_PATTERNS does not cover -- add a pattern rather "
            "than accepting the citations this will produce.",
            100 * unmatched / len(chunks),
        )
        ok = False
    if not hits:
        logger.warning("no chunk mentions both 'deviation' and 'charge' -- wrong corpus?")
        ok = False
    return ok


def write_chunks(
    engine, chunks: list[ingest.Chunk], truncate: bool, skip_embeddings: bool = False
) -> int:
    """Write chunks, optionally without embedding them.

    `skip_embeddings` exists because chunk *text* and chunk *page numbers* have
    nothing to do with the vector index, and requiring a 2.2 GB model to correct
    a wrong page number is a coupling that stops the correction happening. The
    retriever already degrades to BM25 when a query cannot be embedded, so a
    corpus with NULL embeddings is a state the system handles rather than a
    broken one.
    """
    model = None if skip_embeddings else embed.model_name()
    is_postgres = engine.dialect.name == "postgresql"

    with engine.begin() as conn:
        if truncate:
            conn.execute(sql("DELETE FROM regulation_chunks"))
            logger.info("cleared regulation_chunks")

        written = 0
        for start in range(0, len(chunks), BATCH):
            batch = chunks[start : start + BATCH]
            vectors = (
                [None] * len(batch)
                if skip_embeddings
                else embed.embed_passages([c.chunk_text for c in batch])
            )

            for chunk, vector in zip(batch, vectors, strict=True):
                values = None if vector is None else [float(x) for x in vector]
                conn.execute(
                    sql(
                        """
                        INSERT INTO regulation_chunks
                            (doc_name, section, clause, page_no, source_url,
                             effective_date, chunk_text, chunk_id, embedding, embed_model)
                        VALUES
                            (:doc_name, :section, :clause, :page_no, :source_url,
                             :effective_date, :chunk_text, :chunk_id, :embedding, :embed_model)
                        ON CONFLICT (chunk_id) DO UPDATE SET
                            chunk_text = EXCLUDED.chunk_text,
                            -- These three were missing, which made a re-ingest
                            -- unable to fix the thing re-ingests are usually run
                            -- to fix. Note that chunk_id embeds the page number,
                            -- so a changed page inserts a new row rather than
                            -- updating one: use --truncate for a real rebuild.
                            page_no    = EXCLUDED.page_no,
                            clause     = EXCLUDED.clause,
                            section    = EXCLUDED.section,
                            embedding  = EXCLUDED.embedding,
                            embed_model = EXCLUDED.embed_model
                        """
                        if is_postgres
                        else
                        """
                        INSERT OR REPLACE INTO regulation_chunks
                            (doc_name, section, clause, page_no, source_url,
                             effective_date, chunk_text, chunk_id, embedding, embed_model)
                        VALUES
                            (:doc_name, :section, :clause, :page_no, :source_url,
                             :effective_date, :chunk_text, :chunk_id, :embedding, :embed_model)
                        """
                    ),
                    {
                        "doc_name": chunk.doc_name,
                        "section": chunk.section,
                        "clause": chunk.clause,
                        "page_no": chunk.page_no,
                        "source_url": chunk.source_url,
                        "effective_date": chunk.effective_date or None,
                        "chunk_text": chunk.chunk_text,
                        "chunk_id": chunk.stable_id(),
                        # pgvector accepts its text literal form; SQLite stores
                        # the same string and the retriever parses it back.
                        "embedding": None
                        if values is None
                        else (
                            "[" + ",".join(f"{v:.6f}" for v in values) + "]"
                            if is_postgres
                            else __import__("json").dumps(values)
                        ),
                        "embed_model": model,
                    },
                )
                written += 1
            logger.info("embedded and wrote %d/%d", written, len(chunks))

    if is_postgres and not skip_embeddings:
        # Index creation goes last, after the rows exist. See the module docstring.
        with engine.begin() as conn:
            conn.execute(
                sql(
                    "CREATE INDEX IF NOT EXISTS ix_regulation_chunks_embedding_hnsw "
                    "ON regulation_chunks USING hnsw (embedding vector_cosine_ops) "
                    "WITH (m = 16, ef_construction = 64)"
                )
            )
            conn.execute(
                sql(
                    "CREATE INDEX IF NOT EXISTS ix_regulation_chunks_fts "
                    "ON regulation_chunks USING gin (to_tsvector('english', chunk_text))"
                )
            )
        logger.info("ANN and full-text indexes present")

    return written


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()

    chunks = ingest.ingest_all(args.regulations)
    looks_ok = report(chunks)

    if args.jsonl:
        ingest.write_jsonl(chunks, args.jsonl)
        print(f"\nwrote {args.jsonl}")

    if args.dry_run:
        print("\ndry run: nothing written to the database")
        return 0 if looks_ok else 1

    if not args.database_url:
        logger.error("no DATABASE_URL: pass --database-url or set the environment variable")
        return 2

    if args.skip_embeddings:
        print(
            "\nskipping embeddings: chunks are written with a NULL vector and "
            "retrieval stays BM25-only"
        )
    else:
        print(f"\nembedding with {embed.model_name()} (backend={embed.backend()})")
    if embed.backend() == "mock":
        logger.warning(
            "RAG_EMBED_BACKEND=mock produces hash vectors, not semantic ones. "
            "Useful for testing the plumbing, useless for real retrieval."
        )

    engine = create_engine(args.database_url)
    written = write_chunks(
        engine, chunks, truncate=args.truncate, skip_embeddings=args.skip_embeddings
    )

    with engine.connect() as conn:
        rows = conn.execute(
            sql("SELECT embed_model, count(*) FROM regulation_chunks GROUP BY embed_model")
        ).all()
    print(f"\nwrote {written} chunks")
    for model, count in rows:
        print(f"  {count:5d}  {model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
