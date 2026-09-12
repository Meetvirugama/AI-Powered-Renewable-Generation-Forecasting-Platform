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
#
# The bare-number form is the one CERC actually uses. Its notifications number
# regulations as "4. Scope" / "7. Normal Rate of Charges for Deviations", with
# sub-clauses as "(1)", "(2)". Without a pattern for it, 48% of the DSM 2024
# text landed in PREAMBLE with no clause to cite.
#
# Sub-clauses are deliberately NOT split on. "(2)" is not a citable unit on its
# own -- an operator needs "Regulation 6", not "(2)" -- so they stay attached to
# the parent regulation, which is also what keeps a chunk self-contained.
CLAUSE_PATTERNS = [
    re.compile(r"^\s*(?P<id>Regulation\s+\d{1,2}(?:\(\w{1,3}\))*(?:\.\d{1,2})*)\s*[.:\-\u2013]?\s*(?P<title>[^\n]{0,120})", re.I),
    re.compile(r"^\s*(?P<id>Clause\s+\d{1,2}(?:\.\d{1,2})*)\s*[.:\-\u2013]?\s*(?P<title>[^\n]{0,120})", re.I),
    # "7.2.1 Deviation Settlement". End-anchored with a title-like charset so a
    # frequency out of a table -- "50.00 Hz]; and" -- is not read as a clause
    # heading, which is exactly what it did before.
    re.compile(r"^\s*(?P<id>\d{1,2}(?:\.\d{1,2}){1,3})\s+(?P<title>[A-Z][A-Za-z0-9 ,\-()&/'‘’]{2,110})\s*$"),
    # "7. Normal Rate of Charges for Deviations" -- anchored to end-of-line, which
    # is what separates a heading from a numbered sentence that happens to start
    # the same way. A heading occupies its own line; a sentence runs on.
    re.compile(r"^\s*(?P<id>\d{1,2})\.\s+(?P<title>[A-Z][A-Za-z0-9 ,\-()&/'\u2018\u2019]{2,80})\s*$"),
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


_BARE_NUMBER = re.compile(r"^\d{1,2}(?:\.\d{1,2})*$")

# What a bare number is called in a given document. CERC notifications number
# "Regulations"; the Grid Code numbers "Clauses". Emitting the wrong word would
# make the citation itself inaccurate, which is the one thing this pipeline
# cannot afford -- so it comes from the document's metadata, not a guess.
DEFAULT_CLAUSE_PREFIX = "Regulation"


def _match_heading(line: str, clause_prefix: str = DEFAULT_CLAUSE_PREFIX) -> tuple[str, str] | None:
    if len(line) > 200:          # a heading is never a full paragraph
        return None
    for pat in CLAUSE_PATTERNS:
        m = pat.match(line)
        if m:
            clause_id = m.group("id").strip()
            # A citation badge reading "7" tells an operator nothing.
            if _BARE_NUMBER.match(clause_id):
                clause_id = f"{clause_prefix} {clause_id}".strip()
            return clause_id, (m.groupdict().get("title") or "").strip()
    return None


def _clean(text: str) -> str:
    text = re.sub(r"-\n(?=[a-z])", "", text)                 # de-hyphenate wrapped words
    text = re.sub(r"(?<![.\n])\n(?![A-Z0-9\n])", " ", text)  # unwrap soft line breaks
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _snap_to_word(text: str, start: int, limit: int) -> int:
    """Move `start` forward to the beginning of a word.

    The overlap rewinds a fixed number of characters from the end of the last
    chunk, and left alone it lands mid-word far more often than not: 57% of the
    indexed corpus began mid-word. Two things that costs, both invisible unless
    somebody looks at an actual chunk:

    * BM25 tokenises "deviation" as "ation", so the term the query contains is
      simply not in the index for that chunk.
    * The citation snippet a judge clicks through to reads "ly, the Commission
      is of the view", which looks like a broken product.

    Snapping forward gives up a few characters of overlap and buys a chunk that
    begins where a reader would begin. No text is lost: the preceding chunk
    already contains it.
    """
    if start <= 0 or start >= limit:
        return start
    if text[start - 1].isspace():
        return start

    nxt = start
    while nxt < limit and not text[nxt].isspace():
        nxt += 1
    while nxt < limit and text[nxt].isspace():
        nxt += 1
    # If the rest of the window is one unbroken token, keep the original offset
    # rather than collapsing the chunk to nothing.
    return nxt if nxt < limit else start


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
        # The forward cut above respects sentence boundaries; this rewind did
        # not, which is where the mid-word chunks came from.
        start = _snap_to_word(text, max(end - overlap, start + 1), end)
    return [p for p in parts if p]


def chunk_pages(pages: list[tuple[int, str]], doc_meta: dict) -> list[Chunk]:
    """Chunk already-extracted page text. `pages` is [(page_no, text), ...], 1-indexed."""
    chunks: list[Chunk] = []
    clause_prefix = str(doc_meta.get("clause_prefix", DEFAULT_CLAUSE_PREFIX))
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
            hit = _match_heading(line, clause_prefix)
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
