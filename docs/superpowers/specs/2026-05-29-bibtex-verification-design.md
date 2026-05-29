# BibTeX Verification & Export — Design Spec

**Date:** 2026-05-29
**Status:** Draft
**Package:** paperscout v0.1.2 → v0.2.0

## Overview

Add two complementary features to paperscout:

1. **BibTeX export** — `Paper.to_bibtex()` method and `--bibtex` flag on search/match commands, so users can export paper metadata directly as BibTeX entries.
2. **BibTeX verification** — a `verify` CLI command and `BibtexVerifier` class that checks every entry in a `.bib` file against academic databases (via existing backends) and reports which papers are real, uncertain, or likely fabricated.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Verification depth | Title + metadata cross-check | Balance accuracy with practicality; catches fabricated papers with real titles but fake authors/venues |
| Output formats | Console table + annotated `.bib` + JSON report | Matches existing `--json`/`--output` CLI patterns; JSON enables downstream automation |
| Classification | Confidence score (0–100%) with 3 tiers | Granular, actionable; tiers provide quick visual summary |
| Enrichment | Opt-in via `--enrich` flag | Safe by default; users explicitly opt into file modification |
| Backend selection | Smart routing (primary + fallback) with `--source` override | Fast for typical files; mirrors existing `search --source` pattern |
| Overall approach | Integrated (flat module, not subpackage) | Right-sized for current scope; can refactor to subpackage later if needed |

## Architecture

### New module: `paperscout/bibtex.py`

Contains all BibTeX logic in a single module with these components:

- `BibtexVerifier` — main class orchestrating verification
- `_compute_confidence(entry, paper) -> float` — scoring function
- `_smart_routing(entry) -> list[str]` — backend selection per entry
- `_parse_bibtex(path) -> list[dict]` — parse `.bib` file into entry dicts
- `_write_annotated_bibtex(entries, results, path)` — write verified `.bib`
- `_format_verification_report(results) -> Table` — Rich console table

### Modified files

| File | Change |
|------|--------|
| `paperscout/types.py` | Add `Paper.to_bibtex(entry_key, entry_type) -> str` |
| `paperscout/search.py` | Expose `_get_backend` as a public helper for the verifier; or add a `search_by_title_only` method that the verifier can use without shortcut expansion |
| `paperscout/cli.py` | Add `verify` subcommand with args: file, `--source`, `--enrich`, `--output`, `--json`, `--parallel`, `--threshold`. Add `--bibtex` flag to search/match commands. |
| `paperscout/client.py` | Add `verify_bibtex(path, **kwargs)` method |
| `paperscout/__init__.py` | Export `BibtexVerifier` |
| `pyproject.toml` | Add `bibtexparser>=1.4.0` to dependencies; bump version to 0.2.0 |

### No changes to

- `paperscout/backends/` — unchanged; verifier uses existing backends
- `paperscout/similarity.py` — unchanged; reused as-is
- `paperscout/download.py` — unchanged
- `paperscout/formatter.py` — unchanged; verifier has its own formatter

## Confidence Scoring Algorithm

```
score = title_similarity × 0.40
      + author_overlap    × 0.30
      + year_match        × 0.15
      + source_agreement  × 0.15
```

### Components

| Component | Weight | Calculation |
|-----------|--------|-------------|
| Title similarity | 40% | Jaccard token overlap (reuses `_title_similarity`) |
| Author overlap | 30% | Fraction of BibTeX last names found in backend result's authors (case-insensitive) |
| Year match | 15% | 1.0 if exact, 0.5 if ±1 year, 0.0 otherwise |
| Source agreement | 15% | Bonus when multiple backends find the same paper; or when the entry's DOI/arXiv ID matches the backend result |

### Tiers (displayed in reports)

| Tier | Range | Emoji | Label |
|------|-------|-------|-------|
| Verified | ≥80% | 🟢 | High confidence |
| Uncertain | 50–79% | 🟡 | Manual review recommended |
| Suspicious | <50% | 🔴 | Likely fabricated or not found |

### Edge Cases

- No backend returns any result → score 0.0, flagged "Not found in any database"
- BibTeX entry has no title → skipped with warning
- Backends disagree (one finds, another doesn't) → source agreement penalty reduces score
- Backend search fails (network error, API down) → entry marked "Unverified — backend error", not suspicious
- Short titles (< 3 words) → similarity threshold relaxed slightly
- Titles with special LaTeX characters → normalized before comparison

## Smart Backend Routing

Inspects BibTeX entry fields to choose primary + fallback backends:

```
eprint field with "arXiv:" prefix?  → ArxivBackend primary, all others fallback
url field with aclweb/aclanthology? → ACLAnthologyBackend primary, SemanticScholar fallback
dblp/DBLP key field?                → DblpBackend primary, SemanticScholar fallback
doi field?                          → SemanticScholarBackend primary, all others fallback
booktitle with ACL venue names?     → ACLAnthologyBackend primary, all others fallback
No identifiable fields?             → ALL backends (broad search)
```

### Verification workflow per entry

1. Parse entry → extract title, authors, year, identifiers
2. Smart-route → pick primary + fallback backends
3. Search primary backend with title query
4. If ≥80% confidence → stop, return result
5. Otherwise → search fallback backends
6. Aggregate → pick best match across all searched backends
7. Compute final confidence score
8. If `--enrich` → merge discovered metadata into entry

### Performance

- Smart routing hits 1–2 backends per entry on average (vs. 4 without)
- Sequential by default (respects API rate limits)
- `--parallel` flag enables `concurrent.futures` for faster processing (opt-in)

## Paper.to_bibtex()

```python
def to_bibtex(self, entry_key: str | None = None, entry_type: str | None = None) -> str:
```

### Entry type auto-detection

| Source | Default entry type |
|--------|-------------------|
| `acl_anthology` | `@inproceedings` |
| `arxiv` | `@article` |
| `dblp` | `@inproceedings` |
| `semantic_scholar` | Checks venue/categories; defaults to `@article` |

### Citation key auto-generation

`firstAuthorLastName + year + firstSignificantTitleWord`, e.g. `vaswani2017attention`. Sanitized to lowercase alphanumeric. "Significant" means skipping stop words: a, an, the, on, in, of, for, to, and, with, from, by.

### Fields included

Always: `title`, `author`, `year`
When available: `doi`, `url`, `abstract`, `booktitle` (from categories/venue), `eprint` (arXiv ID), `pages` (if available)

## CLI Design

### New command: `verify`

```
paperscout verify <file> [options]

Arguments:
  file                  Path to .bib file to verify

Options:
  -s, --source SRC      Backends to use (comma-separated: arxiv,dblp,etc.)
                        Default: smart routing
  --enrich              Fill in missing fields from discovered metadata
  --threshold FLOAT     Confidence threshold for "suspicious" (default: 0.5)
  --parallel            Enable parallel backend queries
  -o, --output PATH     Write annotated .bib to this path
  -j, --json PATH       Write JSON verification report to this path
```

### Modified commands: `search`, `match`

Added `--bibtex` flag: when set, output results as BibTeX entries instead of table/panel. Combines with `--output` to write a `.bib` file.

## Output Formats

### Console Report (always shown)

Rich table with columns: BibTeX key, title (truncated), confidence %, tier emoji, matched title from backend, notes (e.g., "year mismatch", "no hits"). Footer shows summary counts.

### Annotated .bib (`--output`)

Original `.bib` content with prepended comments per entry:
```
% verification_status: verified | uncertain | suspicious
% verification_score: 0.95
% verification_source: arxiv
% verification_matched_title: Attention Is All You Need
@article{vaswani2017attention, ...
```

With `--enrich`, missing fields (doi, url, abstract) are also injected into the entry body.

### JSON Report (`--json`)

Array of per-entry objects:
```json
[
  {
    "bib_key": "vaswani2017attention",
    "original_title": "Attention Is All You Need",
    "verdict": "verified",
    "confidence": 0.98,
    "tier": "verified",
    "matched_paper": { /* Paper.to_dict() */ },
    "backend_used": "arxiv",
    "discrepancies": [],
    "error": null
  }
]
```

## New Dependency

`bibtexparser>=1.4.0` — mature, well-maintained library for BibTeX parsing and writing. Added to core dependencies (not optional), since both the `verify` command and `Paper.to_bibtex()` use it.

## Test Plan

### New test file: `tests/test_bibtex.py`

| Test class | Coverage |
|------------|----------|
| `TestPaperToBibtex` | Entry types, key generation, field output, missing fields |
| `TestBibtexVerifier` | Exact match, partial match, no match, multi-backend, confidence scoring |
| `TestSmartRouting` | arXiv eprint, ACL URL, DBLP key, DOI, venue detection, fallback |
| `TestConfidenceScoring` | Perfect match (1.0), no match (0.0), year mismatch, author mismatch, multi-backend agreement bonus |
| `TestBibtexParsing` | Valid .bib, malformed entries, empty file, comments, string macros |
| `TestAnnotatedOutput` | Annotated .bib format, `--enrich` field injection |

### Test fixture

`tests/fixtures/sample.bib` — 5 entries:
1. Clearly real (well-known paper with arXiv ID)
2. Clearly real (ACL venue paper)
3. Clearly fabricated (nonsense title)
4. Ambiguous (real-looking title with fake authors)
5. Missing fields (no year, no identifier)

### Existing tests

No changes needed to `test_backends.py`, `test_search.py`, `test_similarity.py`, `test_client.py`.

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Backend network error | Mark entry "Unverified — backend error", continue with remaining entries |
| Malformed .bib file | Parse what bibtexparser can, warn about unparseable lines, continue |
| Empty .bib file | Exit early: "No entries found in <file>" |
| No backends installed | Exit with message: "At least one backend must be installed" |
| All backends fail | Report all entries as "Unverified — all backends unavailable" |
| File encoding issues | Try UTF-8 first, fall back to latin-1 with warning |
| Short title (< 3 words) | Relax similarity threshold; flag in notes |

## Scope Boundaries

**In scope:**
- `Paper.to_bibtex()` export method
- `BibtexVerifier` class with confidence scoring and smart routing
- `verify` CLI command with all flags
- `--bibtex` flag on search/match commands
- Annotated `.bib` output and JSON report
- Test coverage for all new functionality

**Out of scope (future work):**
- BibTeX file deduplication
- BibTeX format conversion (BibTeX ↔ BibLaTeX)
- Automatic paper retraction checking
- Incremental verification (only check new entries since last run)
- Web UI or dashboard
- PDF verification / checksum validation
