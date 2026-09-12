#!/usr/bin/env python
"""Measure recall@k of the retriever against a fixed question set.

    python scripts/eval_retrieval.py
    python scripts/eval_retrieval.py -k 10 --verbose

This is the only objective signal anyone on this project will ever have about
RAG quality. Thirty minutes of work, and without it "the retrieval seems fine"
is the entire quality process.

Target: recall@5 >= 0.7. Below that, fix the *chunker*, not the prompt. A prompt
cannot cite a clause that retrieval never surfaced, and time spent rewording the
system message while recall is 0.4 is time wasted.

Each question declares what a correct retrieval looks like -- an expected
document, an expected clause, or expected keywords in the retrieved text. A
question with no expectation is scored only for "did anything come back", which
is still worth knowing.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from backend.modules.rag import embed, retriever  # noqa: E402

QUESTIONS = Path("tests/rag_eval_questions.json")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-k", type=int, default=5, help="retrieve this many chunks (default 5)")
    p.add_argument("--questions", type=Path, default=QUESTIONS)
    p.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    p.add_argument("--verbose", action="store_true", help="print what was retrieved for each miss")
    p.add_argument("--target", type=float, default=0.7, help="fail below this recall (default 0.7)")
    return p.parse_args()


def hit(question: dict, results: list) -> bool:
    """Did the retrieval surface what this question expects?"""
    if not results:
        return False

    expect_doc = question.get("expect_doc")
    if expect_doc and not any(expect_doc.lower() in (r.doc_name or "").lower() for r in results):
        return False

    expect_clause = question.get("expect_clause")
    if expect_clause and not any(
        expect_clause.lower() in (r.clause or "").lower() for r in results
    ):
        return False

    expect_keywords = question.get("expect_keywords")
    if expect_keywords:
        blob = " ".join((r.chunk_text or "").lower() for r in results)
        if not all(kw.lower() in blob for kw in expect_keywords):
            return False

    return True


def main() -> int:
    args = parse_args()

    if not args.database_url:
        print("no DATABASE_URL: pass --database-url or set the environment variable")
        return 2

    questions = json.loads(args.questions.read_text(encoding="utf-8"))
    session = sessionmaker(bind=create_engine(args.database_url))()

    print(f"embedding backend: {embed.backend()} ({embed.model_name()})")
    if embed.backend() == "mock":
        print("WARNING: mock embeddings are hash vectors. These numbers mean nothing.")

    loaded = retriever.build_bm25(session)
    print(f"corpus: {loaded} chunks indexed for BM25\n")

    hits = 0
    misses: list[tuple[dict, list]] = []

    for question in questions:
        results = retriever.retrieve(
            session, question["q"], rule_year=question.get("rule_year"), k=args.k
        )
        if hit(question, results):
            hits += 1
            mark = "PASS"
        else:
            misses.append((question, results))
            mark = "MISS"
        print(f"[{mark}] {question['q']}")

    recall = hits / len(questions) if questions else 0.0
    print(f"\nrecall@{args.k} = {recall:.2f}  ({hits}/{len(questions)})")

    if args.verbose and misses:
        print("\n--- misses ---")
        for question, results in misses:
            print(f"\nQ: {question['q']}")
            print(f"   expected: { {k: v for k, v in question.items() if k.startswith('expect')} }")
            if not results:
                print("   retrieved: nothing")
            for r in results:
                print(f"   got: {r.doc_name} | {r.clause} | p.{r.page_no} | {r.chunk_text[:90]}...")

    if recall < args.target:
        print(
            f"\nBelow target ({args.target:.2f}). Look at the chunker before the prompt: "
            "check the unmatched-clause rate from scripts/build_index.py --dry-run, and "
            "whether the expected clause survived chunking intact."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
