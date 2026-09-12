"""Clause-aware PDF ingestion for CERC / IEGC regulation documents.

Structure first, size second. A naive 512-character splitter cuts
"Regulation 7(2)(b)" in half and every citation built on it is garbage. Here the
text is split on legal headings, and only then size-bounded *within* a single
clause -- so the clause id attached to a chunk is always the clause the text
actually came from.

The PDF layer (PyMuPDF) is separated from the chunking layer so the chunker can
be unit-tested on plain strings; see tests/test_rag_ingest.py.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger("renewable_platform")

# Ordered most-specific -> least-specific. First match wins.
CLAUSE_PATTERNS = [
    re.compile(r"^\s*(?P<id>Regulation\s+\d{1,2}(?:\(\w{1,3}\))*(?:\.\d{1,2})*)\s*[.:\-\u2013]?\s*(?P<title>[^\n]{0,120})", re.I),
    re.compile(r"^\s*(?P<id>Clause\s+\d{1,2}(?:\.\d{1,2})*)\s*[.:\-\u2013]?\s*(?P<title>[^\n]{0,120})", re.I),
    re.compile(r"^\s*(?P<id>\d{1,2}(?:\.\d{1,2}){1,3})\s+(?P<title>[A-Z][^\n]{0,120})"),
    re.compile(r"^\s*(?P<id>CHAPTER\s+[IVXLC]+)\s*[.:\-\u2013\u2014]?\s*(?P<title>[^\n]{0,120})"),
    re.compile(r"^\s*(?P<id>SCHEDULE\s+[IVXLC0-9]+)\s*[.:\-\u2013\u2014]?\s*(?P<title>[^\n]{0,120})"),
]

MAX_CHARS = 1800        # about 450 tokens of English legal text
OVERLAP_CHARS = 200
MIN_CHARS = 120         # drops running headers, footers and bare page numbers

PREAMBLE = "PREAMBLE"


@dataclass
class Chunk:
    doc_name: str
    section: str
    clause: str
    page_no: int
    source_url: str
    effective_date: str | None
    chunk_text: str
    chunk_index: int

    def stable_id(self) -> str:
        """Deterministic id, so re-running the ingest updates rows instead of duplicating them."""
        return f"{self.doc_name}::{self.clause}::{self.page_no}::{self.chunk_index}"


def _match_heading(line: str) -> tuple[str, str] | None:
    if len(line) > 200:          # a heading is never a full paragraph
        return None
    for pat in CLAUSE_PATTERNS:
        m = pat.match(line)
        if m:
            return m.group("id").strip(), (m.groupdict().get("title") or "").strip()
    return None


def _clean(text: str) -> str:
    text = re.sub(r"-\n(?=[a-z])", "", text)                 # de-hyphenate wrapped words
    text = re.sub(r"(?<![.\n])\n(?![A-Z0-9\n])", " ", text)  # unwrap soft line breaks
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _window(text: str, limit: int = MAX_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Size-bound one clause, cutting on a sentence boundary where one is available."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            cut = max(
                text.rfind(". ", start + limit // 2, end),
                text.rfind(";\n", start + limit // 2, end),
                text.rfind("\n", start + limit // 2, end),
            )
            if cut > 0:
                end = cut + 1
        parts.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [p for p in parts if p]


def chunk_pages(pages: list[tuple[int, str]], doc_meta: dict) -> list[Chunk]:
    """Chunk already-extracted page text. `pages` is [(page_no, text), ...], 1-indexed."""
    chunks: list[Chunk] = []
    cur_clause, cur_section = PREAMBLE, PREAMBLE
    buf: list[str] = []
    buf_page = 1
    idx = 0

    def flush(clause: str, section: str, page: int) -> None:
        nonlocal buf, idx
        body = _clean("\n".join(buf))
        buf = []
        if len(body) < MIN_CHARS:
            return
        for piece in _window(body):
            chunks.append(
                Chunk(
                    doc_name=doc_meta["doc_name"],
                    section=section,
                    clause=clause,
                    page_no=page,
                    source_url=doc_meta.get("url", ""),
                    effective_date=doc_meta.get("effective_date"),
                    chunk_text=piece,
                    chunk_index=idx,
                )
            )
            idx += 1

    for page_no, page_text in pages:
        for line in (page_text or "").split("\n"):
            hit = _match_heading(line)
            if hit:
                # Close the previous clause before switching -- a chunk must never
                # span two clauses.
                flush(cur_clause, cur_section, buf_page)
                cur_clause, title = hit
                if title:
                    cur_section = title[:120]
                buf_page = page_no
                buf.append(line)
            else:
                if not buf:
                    buf_page = page_no
                buf.append(line)
    flush(cur_clause, cur_section, buf_page)
    return chunks


def read_pdf_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """Extract per-page text. Raises if the PDF is image-only (needs OCR)."""
    import fitz  # PyMuPDF; imported lazily so the chunker is usable without it

    doc = fitz.open(pdf_path)
    try:
        pages = [(i, page.get_text("text")) for i, page in enumerate(doc, start=1)]
    finally:
        doc.close()

    extracted = sum(len(t.strip()) for _, t in pages)
    if extracted < 200 * len(pages):
        raise ValueError(
            f"{pdf_path.name}: only {extracted} characters extracted across {len(pages)} pages. "
            "This is almost certainly a scanned, image-only PDF and needs OCR "
            "(pytesseract) before it can be ingested."
        )
    return pages


def ingest_pdf(pdf_path: Path, doc_meta: dict) -> list[Chunk]:
    return chunk_pages(read_pdf_pages(pdf_path), doc_meta)


def ingest_all(reg_dir: Path = Path("regulations")) -> list[Chunk]:
    sources_file = reg_dir / "sources.json"
    sources = json.loads(sources_file.read_text(encoding="utf-8")) if sources_file.exists() else {}
    pdfs = sorted(reg_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(
            f"no PDFs in {reg_dir}/. See regulations/README.md for the download list."
        )
    out: list[Chunk] = []
    for pdf in pdfs:
        meta = dict(sources.get(pdf.name, {}))
        meta.setdefault("doc_name", pdf.stem)
        got = ingest_pdf(pdf, meta)
        logger.info("ingested %s -> %d chunks", pdf.name, len(got))
        out.extend(got)
    return out


def write_jsonl(chunks: list[Chunk], path: Path) -> None:
    path.write_text(
        "\n".join(json.dumps(asdict(c), ensure_ascii=False) for c in chunks),
        encoding="utf-8",
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cs = ingest_all()
    write_jsonl(cs, Path("regulations/chunks.jsonl"))
    print(f"{len(cs)} chunks -> regulations/chunks.jsonl")
