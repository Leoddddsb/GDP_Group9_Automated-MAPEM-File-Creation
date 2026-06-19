# Step 2 File Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Step 2 file-format parsing and generate `extracted_facts.partial.json` from a Step 1 inventory.

**Architecture:** Add one coordinator and focused parser modules. Standard-library parsers run without optional packages; document, CAD, and GIS parsers raise actionable dependency errors when their required package or ODA File Converter is missing.

**Tech Stack:** Python standard library, `python-docx`, `pdfplumber`, `ezdxf`, `fiona`, ODA File Converter.

---

### Task 1: Shared text facts and lightweight parsers

**Files:**
- Create: `src/mapemgen/ingestion/text_facts.py`
- Create: `src/mapemgen/ingestion/ram_text.py`
- Create: `src/mapemgen/ingestion/zip_packages.py`
- Create: `src/mapemgen/ingestion/mova.py`
- Test: `tests/test_extraction.py`

- [ ] Write failing tests for keyword facts, ZIP member classification, and MOVA shallow extraction.
- [ ] Run `python -m unittest tests.test_extraction -v` and verify missing-module failures.
- [ ] Implement line-based keyword extraction and the three lightweight parsers.
- [ ] Re-run the tests and verify they pass.

### Task 2: Document parsers

**Files:**
- Create: `src/mapemgen/ingestion/docx_tables.py`
- Modify: `src/mapemgen/ingestion/pdf_tables.py`
- Test: `tests/test_extraction.py`

- [ ] Write failing tests with patched `docx` and `pdfplumber` boundaries.
- [ ] Run the focused tests and verify missing-function failures.
- [ ] Implement paragraph, table, page-text, and image-page deferral facts.
- [ ] Re-run the focused tests and verify they pass.

### Task 3: GIS and CAD parsers

**Files:**
- Modify: `src/mapemgen/ingestion/gis.py`
- Modify: `src/mapemgen/ingestion/cad.py`
- Test: `tests/test_extraction.py`

- [ ] Write failing tests for GeoJSON, OSM, DXF dependency errors, and DWG ODA dependency errors.
- [ ] Run the focused tests and verify missing-function failures.
- [ ] Implement standard-library GIS parsing, Fiona-backed GIS parsing, ezdxf parsing, and ODA dispatch.
- [ ] Re-run focused tests and verify they pass.

### Task 4: Coordinator and CLI

**Files:**
- Create: `src/mapemgen/ingestion/facts.py`
- Modify: `src/mapemgen/cli.py`
- Test: `tests/test_extraction.py`

- [ ] Write failing tests for stable dispatch, corrupt-file continuation, and CLI output.
- [ ] Run the focused tests and verify missing-function failures.
- [ ] Implement coordinator dispatch and `extract` CLI command.
- [ ] Re-run the focused tests and verify they pass.

### Task 5: Dependencies, documentation, and verification

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`

- [ ] Add parser dependencies and document ODA File Converter.
- [ ] Run `python -m unittest discover -s tests -v`.
- [ ] Inspect `git diff --stat` and `git status --short`.

