"""Chunker tests.

The chunker is tested on plain page text rather than on a PDF, so these run
without PyMuPDF and without committing a fixture PDF. What matters here is the
invariant that makes citations trustworthy: a chunk never spans two clauses, so
the clause id attached to a chunk is the clause the text actually came from.
"""
import pytest

from backend.modules.rag.ingest import (
    MAX_CHARS,
    MIN_CHARS,
    PREAMBLE,
    Chunk,
    _clean,
    _match_heading,
    _window,
    chunk_pages,
)

DOC_META = {
    "doc_name": "CERC_DSM_Amendment_2026",
    "url": "https://cercind.gov.in/2026/amendment.pdf",
    "effective_date": "2026-04-01",
}


def _body(text: str, times: int = 4) -> str:
    """Padding long enough to clear MIN_CHARS."""
    return " ".join([text] * times)


# --------------------------------------------------------------- heading matching
@pytest.mark.parametrize(
    "line,expected",
    [
        ("Regulation 7(2)(b) Deviation charges for sellers", "Regulation 7(2)(b)"),
        # CERC numbers its regulations bare; the prefix is added so a citation
        # badge never reads just "7".
        ("7. Normal Rate of Charges for Deviations", "Regulation 7"),
        ("4. Scope", "Regulation 4"),
        ("Clause 5.1 Tolerance band", "Clause 5.1"),
        ("7.2.1 Deviation Settlement", "Regulation 7.2.1"),
        ("CHAPTER IV - DEVIATION CHARGES", "CHAPTER IV"),
        ("SCHEDULE II Rates", "SCHEDULE II"),
    ],
)
def test_headings_are_recognised(line, expected):
    hit = _match_heading(line)
    assert hit is not None
    assert hit[0] == expected


def test_body_prose_is_not_mistaken_for_a_heading():
    assert _match_heading("the generator shall submit a revised schedule") is None
    assert _match_heading("") is None


def test_a_long_paragraph_is_never_treated_as_a_heading():
    assert _match_heading("7.2 " + "x" * 300) is None


# ------------------------------------------------------------------ chunking rules
def test_a_chunk_never_spans_two_clauses():
    pages = [
        (
            1,
            "Regulation 6 Scheduling\n"
            + _body("The generator shall declare availability for each block.")
            + "\nRegulation 7 Deviation charges\n"
            + _body("Deviation beyond the band attracts charges at the normal rate."),
        )
    ]
    chunks = chunk_pages(pages, DOC_META)
    clauses = {c.clause for c in chunks}
    assert "Regulation 6" in clauses
    assert "Regulation 7" in clauses

    for chunk in chunks:
        if chunk.clause == "Regulation 6":
            assert "normal rate" not in chunk.chunk_text
        if chunk.clause == "Regulation 7":
            assert "declare availability" not in chunk.chunk_text


def test_text_before_the_first_heading_is_kept_as_preamble():
    pages = [(1, _body("These regulations may be called the DSM Regulations."))]
    chunks = chunk_pages(pages, DOC_META)
    assert chunks
    assert chunks[0].clause == PREAMBLE


def test_section_title_is_carried_onto_the_chunk():
    pages = [
        (
            3,
            "Regulation 7(2)(b) Deviation charges for sellers\n"
            + _body("Where the actual injection deviates beyond the tolerance band."),
        )
    ]
    chunk = chunk_pages(pages, DOC_META)[0]
    assert chunk.clause == "Regulation 7(2)(b)"
    assert "Deviation charges for sellers" in chunk.section
    assert chunk.page_no == 3


def test_metadata_needed_for_a_clickable_citation_is_attached():
    pages = [(1, "Regulation 7 Charges\n" + _body("Deviation charges shall apply."))]
    chunk = chunk_pages(pages, DOC_META)[0]
    assert chunk.doc_name == DOC_META["doc_name"]
    assert chunk.source_url == DOC_META["url"]
    assert chunk.effective_date == "2026-04-01"


def test_page_number_tracks_the_page_the_clause_started_on():
    pages = [
        (11, _body("Preamble text that runs on.")),
        (12, "Regulation 9 Pooling\n" + _body("Generators may pool deviation.")),
    ]
    chunks = chunk_pages(pages, DOC_META)
    pooling = [c for c in chunks if c.clause == "Regulation 9"]
    assert pooling and pooling[0].page_no == 12


def test_fragments_shorter_than_the_floor_are_dropped():
    """Running headers, footers and bare page numbers must not become chunks."""
    assert chunk_pages([(1, "14\nCERC\n"), (2, "15\nCERC\n")], DOC_META) == []


def test_chunks_are_size_bounded_within_a_clause():
    long_clause = "Regulation 8 Settlement\n" + _body("Settlement shall be computed. ", 400)
    chunks = chunk_pages([(1, long_clause)], DOC_META)
    assert len(chunks) > 1
    assert all(len(c.chunk_text) <= MAX_CHARS for c in chunks)
    assert all(c.clause == "Regulation 8" for c in chunks)


def test_stable_id_is_deterministic_and_unique_per_chunk():
    pages = [(1, "Regulation 8 Settlement\n" + _body("Settlement shall be computed. ", 400))]
    first = chunk_pages(pages, DOC_META)
    second = chunk_pages(pages, DOC_META)
    ids = [c.stable_id() for c in first]
    assert ids == [c.stable_id() for c in second]  # re-ingest is idempotent
    assert len(ids) == len(set(ids))


def test_empty_input_produces_no_chunks():
    assert chunk_pages([], DOC_META) == []
    assert chunk_pages([(1, "")], DOC_META) == []


# ------------------------------------------------------------------------ helpers
def test_clean_rejoins_hyphenated_line_wraps():
    assert "deviation" in _clean("devi-\nation charges apply")


def test_window_overlaps_so_a_sentence_split_across_chunks_is_still_retrievable():
    text = "A. " * (MAX_CHARS // 2)
    parts = _window(text)
    assert len(parts) > 1
    assert all(len(p) <= MAX_CHARS for p in parts)


def test_window_leaves_short_text_alone():
    text = "x" * (MIN_CHARS + 10)
    assert _window(text) == [text]


def test_chunk_dataclass_round_trips_its_id():
    chunk = Chunk(
        doc_name="D", section="S", clause="Regulation 1", page_no=2,
        source_url="u", effective_date=None, chunk_text="t", chunk_index=3,
    )
    assert chunk.stable_id() == "D::Regulation 1::2::3"
