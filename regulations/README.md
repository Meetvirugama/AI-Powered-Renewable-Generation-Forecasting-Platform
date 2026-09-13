# Regulation Corpus

The source documents the copilot cites. **Commit the PDFs** — they are the corpus, and the
index build has to be reproducible from a clean clone. They are a few MB in total.

## What goes here

| File | Document | Source |
|---|---|---|
| `CERC_DSM_Regulations_2024.pdf` | CERC (Deviation Settlement Mechanism and related matters) Regulations, 2024 | cercind.gov.in → Regulations |
| `CERC_DSM_Amendment_2025.pdf` | 2025 amendment to the DSM Regulations | cercind.gov.in → Regulations |
| `CERC_DSM_StatementOfReasons_2024.pdf` | Statement of Reasons for the 2024 Regulations: the Commission's reasoning, not operative law | cercind.gov.in → Regulations |
| `sources.json` | Per-file metadata: title, URL, effective date, sha256 | generated, see below |
| `chunks.jsonl` | Chunker output, for inspection | generated, gitignored |

The 2026 X-trajectory is not a separate document; it is written into the 2024 principal
regulations. The Indian Electricity Grid Code (IEGC 2023) is not yet in the corpus, and adding it
is the largest single improvement available to retrieval quality (see `docs/roadmap.md`, R1).

The filename matters. The retriever reads the year out of it to honour the regulation-year
slider: with `rule_year=2024`, any document whose name carries a later year is excluded from
retrieval. Name a file `CERC_DSM_Amendment_2025.pdf` and that works; name it
`amendment_final_v2.pdf` and the copilot will happily cite the 2025 amendment while the UI
reads 2024.

## After adding or replacing a PDF

```bash
# 1. Record the hash and size, and fill in title / url / effective_date by hand.
python scripts/hash_regulations.py

# 2. Check the chunker before embedding anything. This is the step people skip.
python scripts/build_index.py --dry-run

# 3. Build the index.
python scripts/build_index.py --truncate

# 4. Confirm retrieval actually improved.
python scripts/eval_retrieval.py --verbose
```

## `sources.json`

Not optional. Every citation the UI renders carries a `url` taken from here, and a judge who
clicks a citation badge and lands on a dead link does more damage to the project's credibility
than a wrong number would. Fill in a real, working, deep link per document.

## If a PDF has no extractable text

`scripts/build_index.py --dry-run` fails loudly on scanned, image-only PDFs rather than
indexing thousands of empty strings. If that happens, either find a text-layer version of the
document (CERC usually publishes one) or OCR it:

```bash
pip install pytesseract pdf2image
# then pre-process into a text-layer PDF before placing it here
```

Discover this on the day you add the document, not the day before judging.
