#!/usr/bin/env python
"""Record sha256 and size for every regulation PDF in regulations/sources.json.

    python scripts/hash_regulations.py
    python scripts/hash_regulations.py --check     # verify, change nothing

The hash pins which revision of a regulation the index was built from. CERC
re-publishes PDFs at the same URL after corrections, and a corpus silently built
from a different revision than the one cited is not something anyone would catch
by eye.

Descriptive fields (title, url, effective_date) are never overwritten -- they are
filled in by hand and this script preserves them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PLACEHOLDER = "FILL_ME"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=Path("regulations"))
    parser.add_argument("--check", action="store_true", help="verify hashes, write nothing")
    args = parser.parse_args()

    sources_path = args.dir / "sources.json"
    sources = json.loads(sources_path.read_text(encoding="utf-8")) if sources_path.exists() else {}

    pdfs = sorted(args.dir.glob("*.pdf"))
    if not pdfs:
        print(f"no PDFs in {args.dir}/ -- see {args.dir}/README.md for the download list")
        return 1

    changed, drifted, incomplete = [], [], []

    for pdf in pdfs:
        entry = sources.get(pdf.name, {})
        digest = sha256(pdf)

        if args.check:
            recorded = entry.get("sha256")
            if recorded and recorded != PLACEHOLDER and recorded != digest:
                drifted.append(pdf.name)
        elif entry.get("sha256") != digest:
            changed.append(pdf.name)

        entry.setdefault("doc_name", pdf.stem)
        entry.setdefault("title", PLACEHOLDER)
        entry.setdefault("url", PLACEHOLDER)
        entry.setdefault("effective_date", PLACEHOLDER)
        entry["sha256"] = digest
        entry["bytes"] = pdf.stat().st_size
        sources[pdf.name] = entry

        if any(entry.get(f) in (None, PLACEHOLDER) for f in ("title", "url", "effective_date")):
            incomplete.append(pdf.name)

        print(f"{pdf.name}  {digest[:16]}...  {pdf.stat().st_size:,} bytes")

    if args.check:
        if drifted:
            print(f"\nhash mismatch: {', '.join(drifted)}")
            print("The PDF changed since the index was built. Re-run scripts/build_index.py.")
            return 1
        print("\nall hashes match")
        return 0

    sources_path.write_text(json.dumps(sources, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nupdated {sources_path}" + (f" ({len(changed)} changed)" if changed else ""))

    if incomplete:
        print(
            f"\nStill needs a real title / url / effective_date: {', '.join(incomplete)}\n"
            "The url is rendered on every citation badge, and a dead link costs more "
            "credibility than a wrong number."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
