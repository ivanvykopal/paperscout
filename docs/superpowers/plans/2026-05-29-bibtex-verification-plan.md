# BibTeX Verification & Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add BibTeX export (`Paper.to_bibtex()`) and verification (`BibtexVerifier` + `verify` CLI command) to paperscout.

**Architecture:** Single new module `paperscout/bibtex.py` containing all BibTeX logic. Modify existing files minimally to integrate new features. Follow TDD: write tests first, then implementation.

**Tech Stack:** Python 3.8+, bibtexparser>=1.4.0, existing backends (arxiv, dblp, s2cli, acl_anthology), Rich for CLI output.

---

## File Structure

### Files to Create
- `paperscout/bibtex.py` — BibTeX parsing, verification, export logic
- `tests/test_bibtex.py` — Tests for all BibTeX functionality
- `tests/fixtures/sample.bib` — Test fixture with 5 entries

### Files to Modify
- `paperscout/types.py:11-82` — Add `to_bibtex()` method to Paper class
- `paperscout/search.py:225-250` — Expose backend access for verifier
- `paperscout/cli.py:17-168` — Add `verify` command, `--bibtex` flag to search/match
- `paperscout/client.py:17-79` — Add `verify_bibtex()` method
- `paperscout/__init__.py:1-30` — Export `BibtexVerifier`
- `pyproject.toml:1-72` — Add bibtexparser dependency, bump version to 0.2.0

---

## Task 1: Add bibtexparser dependency

**Files:**
- Modify: `pyproject.toml:39-43`

- [ ] **Step 1: Update dependencies**

```toml
# pyproject.toml lines 39-43
dependencies = [
    "requests>=2.28.0",
    "beautifulsoup4>=4.12.0",
    "rich>=13.0.0",
    "bibtexparser>=1.4.0",
]
```

- [ ] **Step 2: Bump version**

```toml
# pyproject.toml line 7
version = "0.2.0"
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add bibtexparser dependency and bump to 0.2.0"
```

---

## Task 2: Add Paper.to_bibtex() method

**Files:**
- Modify: `paperscout/types.py:11-82`
- Test: `tests/test_bibtex.py` (created in Task 6)

- [ ] **Step 1: Write failing test**

```python
# tests/test_bibtex.py - TestPaperToBibtex class
import unittest
from paperscout.types import Paper


class TestPaperToBibtex(unittest.TestCase):
    """Test cases for Paper.to_bibtex() method."""

    def setUp(self):
        self.paper = Paper(
            title="Attention Is All You Need",
            authors=["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
            year=2017,
            abstract="We propose a new simple network architecture...",
            source="arxiv",
            identifier="1706.03762",
            url="https://arxiv.org/abs/1706.03762",
            pdf_url="https://arxiv.org/pdf/1706.03762.pdf",
            published="2017-06-12",
            categories=["cs.LG", "cs.CL"],
        )

    def test_to_bibtex_auto_key_generation(self):
        """Test automatic citation key generation."""
        result = self.paper.to_bibtex()
        self.assertIn("vaswani2017", result.lower())
        self.assertIn("attention", result.lower())

    def test_to_bibtex_custom_key(self):
        """Test custom citation key."""
        result = self.paper.to_bibtex(entry_key="mykey")
        self.assertIn("@article{mykey,", result)

    def test_to_bibtex_entry_type_arxiv(self):
        """Test arxiv source produces @article."""
        result = self.paper.to_bibtex()
        self.assertIn("@article", result)

    def test_to_bibtex_entry_type_acl(self):
        """Test acl_anthology source produces @inproceedings."""
        acl_paper = Paper(
            title="Test Paper",
            authors=["John Doe"],
            year=2020,
            abstract=None,
            source="acl_anthology",
            identifier="P20-1001",
            url="https://aclanthology.org/P20-1001",
            pdf_url="https://aclanthology.org/P20-1001.pdf",
            published=None,
            categories=["ACL"],
        )
        result = acl_paper.to_bibtex()
        self.assertIn("@inproceedings", result)

    def test_to_bibtex_required_fields(self):
        """Test that required fields are always present."""
        result = self.paper.to_bibtex()
        self.assertIn("title =", result)
        self.assertIn("author =", result)
        self.assertIn("year =", result)

    def test_to_bibtex_optional_fields(self):
        """Test optional fields when available."""
        result = self.paper.to_bibtex()
        self.assertIn("url =", result)
        self.assertIn("abstract =", result)

    def test_to_bibtex_no_author_last_name(self):
        """Test handling of authors without clear last name."""
        paper = Paper(
            title="Test",
            authors=[],
            year=2020,
            abstract=None,
            source="arxiv",
            identifier="",
            url="",
            pdf_url=None,
            published=None,
            categories=[],
        )
        result = paper.to_bibtex()
        # Should handle gracefully with placeholder key
        self.assertIn("@article", result)
        self.assertIn("2020", result)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_bibtex.py::TestPaperToBibtex -v
# Expected: NameError or AttributeError - to_bibtex not defined yet
```

- [ ] **Step 3: Implement Paper.to_bibtex()**

Add to `paperscout/types.py` after the `from_dict` method:

```python
    def to_bibtex(self, entry_key: str | None = None, entry_type: str | None = None) -> str:
        """
        Export the paper as a BibTeX entry.

        Args:
            entry_key: BibTeX citation key (auto-generated if None).
            entry_type: BibTeX entry type like 'article', 'inproceedings' (auto-detected if None).

        Returns:
            Formatted BibTeX entry string.
        """
        # Auto-detect entry type based on source
        if entry_type is None:
            entry_type = self._infer_entry_type()

        # Generate or use provided citation key
        if entry_key is None:
            entry_key = self._generate_citation_key()

        # Build BibTeX fields
        fields = {
            "title": self.title.replace("{", "{{").replace("}", "}}"),
            "author": " and ".join(self.authors) if self.authors else "Unknown",
            "year": str(self.year) if self.year else "",
        }

        # Add optional fields
        if self.identifier and self.source == "arxiv":
            fields["eprint"] = self.identifier
        if self.url:
            fields["url"] = self.url
        if self.abstract:
            fields["abstract"] = self.abstract.replace("{", "{{").replace("}", "}}")
        if self.categories and self.source == "acl_anthology":
            fields["booktitle"] = self.categories[0].replace("{", "{{").replace("}", "}}")

        # Filter empty fields
        fields = {k: v for k, v in fields.items() if v}

        # Format BibTeX entry
        field_str = ",\n    ".join(f"{k} = {{{v}}}" for k, v in fields.items())
        return f"@{entry_type}{{{entry_key},\n    {field_str}\n}}"

    def _infer_entry_type(self) -> str:
        """Infer BibTeX entry type from source."""
        if self.source == "acl_anthology":
            return "inproceedings"
        elif self.source == "dblp":
            return "inproceedings"
        elif self.source == "semantic_scholar":
            # Check venue for clues
            if self.categories and any(v in "acl emnlp naacl iclr".lower() for v in self.categories):
                return "inproceedings"
            return "article"
        else:  # arxiv default
            return "article"

    def _generate_citation_key(self) -> str:
        """Generate a citation key from author, year, and title."""
        STOP_WORDS = {"a", "an", "the", "on", "in", "of", "for", "to", "and", "with", "from", "by"}

        # Get first author's last name
        if self.authors:
            first_author = self.authors[0]
            parts = first_author.strip().split()
            last_name = parts[-1].lower() if parts else ""
        else:
            last_name = ""

        # Get significant word from title
        title_words = self.title.lower().split()
        significant_words = [w for w in title_words if w not in STOP_WORDS and len(w) > 2]
        significant_word = significant_words[0] if significant_words else ""

        # Combine into key
        key_parts = [p for p in [last_name, str(self.year) if self.year else "", significant_word] if p]
        key = "".join(key_parts[:3])  # Limit to 3 parts

        # Sanitize: only alphanumeric
        key = "".join(c for c in key if c.isalnum()).lower()
        return key or "unknown"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_bibtex.py::TestPaperToBibtex -v
# Expected: All tests pass
```

- [ ] **Step 5: Commit**

```bash
git add paperscout/types.py tests/test_bibtex.py
git commit -m "feat: add Paper.to_bibtex() method with auto key generation"
```

---

## Task 3: Create BibtexVerifier core structure

**Files:**
- Create: `paperscout/bibtex.py`
- Test: `tests/test_bibtex.py` (add TestBibtexVerifier class)

- [ ] **Step 1: Write failing test for verifier initialization**

```python
# tests/test_bibtex.py - add after TestPaperToBibtex
class TestBibtexVerifier(unittest.TestCase):
    """Test cases for BibtexVerifier class."""

    def test_verifier_initialization(self):
        """Test BibtexVerifier can be instantiated."""
        from paperscout.bibtex import BibtexVerifier
        verifier = BibtexVerifier()
        self.assertIsNotNone(verifier)

    def test_verify_empty_file(self):
        """Test verifying an empty .bib file returns empty results."""
        from paperscout.bibtex import BibtexVerifier
        import tempfile
        import os

        verifier = BibtexVerifier()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.bib', delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            results = verifier.verify_file(temp_path)
            self.assertEqual(len(results), 0)
        finally:
            os.unlink(temp_path)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_bibtex.py::TestBibtexVerifier -v
# Expected: ModuleNotFoundError - bibtex module doesn't exist yet
```

- [ ] **Step 3: Create paperscout/bibtex.py with basic structure**

```python
"""
BibTeX parsing, verification, and export functionality.

This module provides tools for verifying BibTeX entries against academic
databases and exporting Paper objects as BibTeX entries.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import bibtexparser
from bibtexparser.middlewares import merge_duplicate_keys, split_name_onto_first_last
from rich.table import Table

from paperscout.search import PaperSearcher
from paperscout.similarity import _title_similarity
from paperscout.types import Paper


@dataclass
class VerificationResult:
    """Result of verifying a single BibTeX entry."""

    bib_key: str
    original_title: str
    confidence: float
    verdict: str  # "verified", "uncertain", "suspicious"
    matched_paper: Paper | None
    backend_used: str | None
    discrepancies: list[str]
    error: str | None
    enriched_entry: dict | None = None


class BibtexVerifier:
    """Verify BibTeX entries against academic databases."""

    # Confidence thresholds
    VERIFIED_THRESHOLD = 0.80
    UNCERTAIN_THRESHOLD = 0.50

    def __init__(self, threshold: float = 0.50):
        """
        Initialize the BibTeX verifier.

        Args:
            threshold: Confidence threshold below which entries are marked suspicious.
        """
        self.threshold = threshold
        self.searcher = PaperSearcher()

    def verify_file(
        self,
        path: str,
        sources: list[str] | None = None,
        enrich: bool = False,
        parallel: bool = False,
    ) -> list[VerificationResult]:
        """
        Verify all entries in a BibTeX file.

        Args:
            path: Path to the .bib file.
            sources: Specific backends to use (None = smart routing).
            enrich: Whether to enrich entries with discovered metadata.
            parallel: Whether to run backend queries in parallel.

        Returns:
            List of VerificationResult objects.
        """
        entries = self._parse_bibtex(path)

        if not entries:
            return []

        results = []
        for entry in entries:
            result = self._verify_entry(entry, sources, enrich)
            results.append(result)

        return results

    def _parse_bibtex(self, path: str) -> list[dict]:
        """Parse a BibTeX file into a list of entry dictionaries."""
        # TODO: Implement
        pass

    def _verify_entry(
        self,
        entry: dict,
        sources: list[str] | None,
        enrich: bool,
    ) -> VerificationResult:
        """Verify a single BibTeX entry."""
        # TODO: Implement
        pass
```

- [ ] **Step 4: Run test to verify it passes (basic structure)**

```bash
pytest tests/test_bibtex.py::TestBibtexVerifier::test_verifier_initialization -v
pytest tests/test_bibtex.py::TestBibtexVerifier::test_verify_empty_file -v
```

- [ ] **Step 5: Commit**

```bash
git add paperscout/bibtex.py tests/test_bibtex.py
git commit -m "feat: add BibtexVerifier basic structure"
```

---

## Task 4: Implement BibTeX parsing

**Files:**
- Modify: `paperscout/bibtex.py:_parse_bibtex`
- Test: `tests/test_bibtex.py::TestBibtexParsing`

- [ ] **Step 1: Write failing test for parsing**

```python
# tests/test_bibtex.py - add TestBibtexParsing class
class TestBibtexParsing(unittest.TestCase):
    """Test cases for BibTeX parsing functions."""

    def test_parse_valid_bibtex(self):
        """Test parsing a valid .bib file."""
        from paperscout.bibtex import BibtexVerifier
        import tempfile
        import os

        verifier = BibtexVerifier()
        bib_content = '''
@article{vaswani2017attention,
  title={Attention Is All You Need},
  author={Vaswani, Ashish and Shazeer, Noam},
  year={2017}
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.bib', delete=False) as f:
            f.write(bib_content)
            temp_path = f.name

        try:
            entries = verifier._parse_bibtex(temp_path)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["TITLE"], "Attention Is All You Need")
        finally:
            os.unlink(temp_path)

    def test_parse_empty_file(self):
        """Test parsing an empty file."""
        from paperscout.bibtex import BibtexVerifier
        import tempfile
        import os

        verifier = BibtexVerifier()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.bib', delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            entries = verifier._parse_bibtex(temp_path)
            self.assertEqual(len(entries), 0)
        finally:
            os.unlink(temp_path)

    def test_parse_multiple_entries(self):
        """Test parsing multiple entries."""
        from paperscout.bibtex import BibtexVerifier
        import tempfile
        import os

        verifier = BibtexVerifier()
        bib_content = '''
@article{a, title={A}, author={A}, year={2020}}
@inproceedings{b, title={B}, author={B}, year={2021}}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.bib', delete=False) as f:
            f.write(bib_content)
            temp_path = f.name

        try:
            entries = verifier._parse_bibtex(temp_path)
            self.assertEqual(len(entries), 2)
        finally:
            os.unlink(temp_path)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_bibtex.py::TestBibtexParsing -v
```

- [ ] **Step 3: Implement _parse_bibtex**

```python
def _parse_bibtex(self, path: str) -> list[dict]:
    """
    Parse a BibTeX file into a list of entry dictionaries.

    Args:
        path: Path to the .bib file.

    Returns:
        List of entry dictionaries. Keys are uppercase (e.g., "TITLE", "AUTHOR").
    """
    import bibtexparser
    from bibtexparser.middlewares import merge_duplicate_keys, split_name_onto_first_last

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        # Fallback to latin-1
        with open(path, "r", encoding="latin-1") as f:
            content = f.read()

    library = bibtexparser.parse_string(content)
    entries = []

    for entry in library.entries:
        # Convert to dict with uppercase keys
        entry_dict = {}
        for key, value in entry.items():
            entry_dict[key.upper()] = value
        entry_dict["_KEY"] = entry.get("key", "")
        entries.append(entry_dict)

    return entries
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_bibtex.py::TestBibtexParsing -v
```

- [ ] **Step 5: Commit**

```bash
git add paperscout/bibtex.py tests/test_bibtex.py
git commit -m "feat: implement BibTeX parsing with bibtexparser"
```

---

## Task 5: Implement smart backend routing

**Files:**
- Modify: `paperscout/bibtex.py:_smart_routing`
- Test: `tests/test_bibtex.py::TestSmartRouting`

- [ ] **Step 1: Write failing test for routing**

```python
# tests/test_bibtex.py - add TestSmartRouting class
class TestSmartRouting(unittest.TestCase):
    """Test cases for smart backend routing."""

    def setUp(self):
        from paperscout.bibtex import BibtexVerifier
        self.verifier = BibtexVerifier()

    def test_route_arxiv_eprint(self):
        """Test routing for arXiv eprint field."""
        entry = {"EPRINT": "arXiv:1706.03762", "TITLE": "Test"}
        primary, fallbacks = self.verifier._smart_routing(entry)
        self.assertEqual(primary, "arxiv")

    def test_route_acl_url(self):
        """Test routing for ACL anthology URL."""
        entry = {"URL": "https://aclanthology.org/P20-1001", "TITLE": "Test"}
        primary, fallbacks = self.verifier._smart_routing(entry)
        self.assertEqual(primary, "acl_anthology")

    def test_route_doi(self):
        """Test routing for DOI field."""
        entry = {"DOI": "10.1234/example", "TITLE": "Test"}
        primary, fallbacks = self.verifier._smart_routing(entry)
        self.assertEqual(primary, "semantic_scholar")

    def test_route_no_identifiers(self):
        """Test routing when no identifiers present."""
        entry = {"TITLE": "Some Paper Title", "AUTHOR": "John Doe"}
        primary, fallbacks = self.verifier._smart_routing(entry)
        self.assertIsNone(primary)  # Will search all backends
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_bibtex.py::TestSmartRouting -v
```

- [ ] **Step 3: Implement _smart_routing**

```python
def _smart_routing(self, entry: dict) -> tuple[str | None, list[str]]:
    """
    Determine which backends to search based on entry fields.

    Args:
        entry: BibTeX entry dictionary.

    Returns:
        Tuple of (primary_backend, fallback_backends).
        If primary is None, search all backends.
    """
    eprint = entry.get("EPRINT", "").lower()
    url = entry.get("URL", "").lower()
    doi = entry.get("DOI", "")
    dblp_key = entry.get("DBLP", "") or entry.get("DBLPKEY", "")
    booktitle = entry.get("BOOKTITLE", "").lower()

    # ArXiv eprint
    if "arxiv:" in eprint or eprint.startswith("10."):
        return "arxiv", ["acl_anthology", "dblp", "semantic_scholar"]

    # ACL Anthology URL
    if "aclanthology" in url or "aclweb" in url:
        return "acl_anthology", ["semantic_scholar"]

    # DBLP key
    if dblp_key:
        return "dblp", ["semantic_scholar"]

    # DOI - Semantic Scholar handles DOI lookup well
    if doi:
        return "semantic_scholar", ["arxiv", "dblp", "acl_anthology"]

    # ACL venue in booktitle
    acl_venues = ["acl", "emnlp", "naacl", "coling", "acl-iit"]
    if any(venue in booktitle for venue in acl_venues):
        return "acl_anthology", ["arxiv", "dblp", "semantic_scholar"]

    # No identifiable fields - search all
    return None, []
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_bibtex.py::TestSmartRouting -v
```

- [ ] **Step 5: Commit**

```bash
git add paperscout/bibtex.py tests/test_bibtex.py
git commit -m "feat: implement smart backend routing"
```

---

## Task 6: Implement confidence scoring

**Files:**
- Modify: `paperscout/bibtex.py:_compute_confidence`
- Test: `tests/test_bibtex.py::TestConfidenceScoring`

- [ ] **Step 1: Write failing test for scoring**

```python
# tests/test_bibtex.py - add TestConfidenceScoring class
class TestConfidenceScoring(unittest.TestCase):
    """Test cases for confidence score calculation."""

    def setUp(self):
        from paperscout.bibtex import BibtexVerifier
        self.verifier = BibtexVerifier()

    def test_perfect_match(self):
        """Test perfect match returns 1.0."""
        entry = {
            "TITLE": "Attention Is All You Need",
            "AUTHOR": "Vaswani, Ashish",
            "YEAR": "2017",
        }
        paper = Paper(
            title="Attention Is All You Need",
            authors=["Ashish Vaswani"],
            year=2017,
            abstract=None,
            source="arxiv",
            identifier="1706.03762",
            url="",
            pdf_url=None,
            published=None,
            categories=[],
        )
        score = self.verifier._compute_confidence(entry, paper)
        self.assertAlmostEqual(score, 1.0, places=2)

    def test_no_match(self):
        """Test completely different entry returns low score."""
        entry = {
            "TITLE": "Quantum Cooking Recipes",
            "AUTHOR": "Jane Smith",
            "YEAR": "2025",
        }
        paper = Paper(
            title="Attention Is All You Need",
            authors=["Ashish Vaswani"],
            year=2017,
            abstract=None,
            source="arxiv",
            identifier="1706.03762",
            url="",
            pdf_url=None,
            published=None,
            categories=[],
        )
        score = self.verifier._compute_confidence(entry, paper)
        self.assertLess(score, 0.3)

    def test_year_mismatch(self):
        """Test year mismatch reduces score."""
        entry = {
            "TITLE": "Attention Is All You Need",
            "AUTHOR": "Vaswani, Ashish",
            "YEAR": "2018",  # Wrong year
        }
        paper = Paper(
            title="Attention Is All You Need",
            authors=["Ashish Vaswani"],
            year=2017,
            abstract=None,
            source="arxiv",
            identifier="1706.03762",
            url="",
            pdf_url=None,
            published=None,
            categories=[],
        )
        score = self.verifier._compute_confidence(entry, paper)
        # Should be lower than perfect match but still decent
        self.assertLess(score, 1.0)
        self.assertGreater(score, 0.7)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_bibtex.py::TestConfidenceScoring -v
```

- [ ] **Step 3: Implement _compute_confidence**

```python
def _compute_confidence(self, entry: dict, paper: Paper) -> tuple[float, list[str]]:
    """
    Compute confidence score for a paper matching an entry.

    Args:
        entry: BibTeX entry dictionary.
        paper: Matched Paper object.

    Returns:
        Tuple of (confidence_score, list_of_discrepancies).
    """
    discrepancies = []

    # Title similarity (40%)
    entry_title = entry.get("TITLE", "")
    title_sim = _title_similarity(entry_title, paper.title)
    title_score = title_sim * 0.40

    # Author overlap (30%)
    entry_authors = self._parse_authors_field(entry.get("AUTHOR", ""))
    author_overlap = self._compute_author_overlap(entry_authors, paper.authors)
    author_score = author_overlap * 0.30
    if author_overlap < 0.5 and entry_authors:
        discrepancies.append("low author overlap")

    # Year match (15%)
    entry_year = self._parse_year(entry.get("YEAR", ""))
    year_score = self._compute_year_score(entry_year, paper.year)
    if entry_year and paper.year and entry_year != paper.year:
        discrepancies.append(f"year mismatch: {entry_year} vs {paper.year}")

    # Source agreement (15%)
    source_score = 0.15  # Full credit since we found it in one backend
    # Could add bonus if multiple backends agree

    total_score = title_score + author_score + year_score + source_score

    return total_score, discrepancies

def _parse_authors_field(self, author_field: str) -> list[str]:
    """Parse BibTeX author field into list of names."""
    if not author_field:
        return []
    # Handle "Last, First and Last, Second" format
    authors = re.split(r"\s+and\s+", author_field, flags=re.IGNORECASE)
    result = []
    for author in authors:
        author = author.strip()
        if "," in author:
            # "Last, First" format
            parts = author.split(",", 1)
            result.append(parts[0].strip())  # Just last name
        else:
            # "First Last" format
            parts = author.split()
            if parts:
                result.append(parts[-1])  # Just last name
    return [a.lower() for a in result]

def _compute_author_overlap(self, entry_authors: list[str], paper_authors: list[str]) -> float:
    """Compute fraction of entry authors found in paper authors."""
    if not entry_authors or not paper_authors:
        return 0.0

    # Extract last names from paper authors
    paper_last_names = set()
    for author in paper_authors:
        parts = author.strip().split()
        if parts:
            paper_last_names.add(parts[-1].lower())

    # Count matches
    matches = sum(1 for a in entry_authors if a in paper_last_names)
    return matches / len(entry_authors)

def _parse_year(self, year_field: str) -> int | None:
    """Parse year from BibTeX year field."""
    if not year_field:
        return None
    try:
        return int(str(year_field)[:4])
    except (ValueError, TypeError):
        return None

def _compute_year_score(self, entry_year: int | None, paper_year: int | None) -> float:
    """Compute year match score."""
    if entry_year is None or paper_year is None:
        return 0.5  # Neutral if missing

    if entry_year == paper_year:
        return 1.0
    elif abs(entry_year - paper_year) <= 1:
        return 0.5
    else:
        return 0.0
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_bibtex.py::TestConfidenceScoring -v
```

- [ ] **Step 5: Commit**

```bash
git add paperscout/bibtex.py tests/test_bibtex.py
git commit -m "feat: implement confidence scoring algorithm"
```

---

## Task 7: Implement entry verification

**Files:**
- Modify: `paperscout/bibtex.py:_verify_entry`
- Test: `tests/test_bibtex.py::TestBibtexVerifier` (more tests)

- [ ] **Step 1: Write failing test for full verification**

```python
# tests/test_bibtex.py - extend TestBibtexVerifier
class TestBibtexVerifier(unittest.TestCase):
    # ... previous tests ...

    def test_verify_single_entry_mocked(self):
        """Test verifying a single entry with mocked backend."""
        from paperscout.bibtex import BibtexVerifier, VerificationResult
        from unittest.mock import patch, MagicMock

        verifier = BibtexVerifier()

        # Mock the searcher
        mock_paper = Paper(
            title="Attention Is All You Need",
            authors=["Ashish Vaswani"],
            year=2017,
            abstract=None,
            source="arxiv",
            identifier="1706.03762",
            url="",
            pdf_url=None,
            published=None,
            categories=[],
        )

        with patch.object(verifier.searcher, 'search', return_value=[mock_paper]):
            entry = {
                "_KEY": "vaswani2017",
                "TITLE": "Attention Is All You Need",
                "AUTHOR": "Vaswani, Ashish",
                "YEAR": "2017",
            }
            result = verifier._verify_entry(entry, None, False)

            self.assertEqual(result.bib_key, "vaswani2017")
            self.assertEqual(result.verdict, "verified")
            self.assertGreater(result.confidence, 0.8)
            self.assertIsNotNone(result.matched_paper)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_bibtex.py::TestBibtexVerifier::test_verify_single_entry_mocked -v
```

- [ ] **Step 3: Implement _verify_entry**

```python
def _verify_entry(
    self,
    entry: dict,
    sources: list[str] | None,
    enrich: bool,
) -> VerificationResult:
    """
    Verify a single BibTeX entry.

    Args:
        entry: BibTeX entry dictionary.
        sources: Specific backends to use.
        enrich: Whether to enrich the entry.

    Returns:
        VerificationResult.
    """
    bib_key = entry.get("_KEY", "unknown")
    title = entry.get("TITLE", "")

    if not title:
        return VerificationResult(
            bib_key=bib_key,
            original_title="",
            confidence=0.0,
            verdict="suspicious",
            matched_paper=None,
            backend_used=None,
            discrepancies=["no title"],
            error="Entry has no title",
        )

    # Smart routing
    primary, fallbacks = self._smart_routing(entry)

    # Build search sources list
    if sources:
        search_sources = sources
    elif primary:
        search_sources = [primary] + fallbacks
    else:
        search_sources = ["all"]

    # Search for the paper
    best_paper: Paper | None = None
    best_source: str | None = None
    best_confidence = 0.0
    discrepancies: list[str] = []

    for source in search_sources:
        try:
            papers = self.searcher.search(title, source=source, limit=5)
            if not papers:
                continue

            # Find best match
            for paper in papers:
                conf, disc = self._compute_confidence(entry, paper)
                if conf > best_confidence:
                    best_confidence = conf
                    best_paper = paper
                    best_source = source
                    discrepancies = disc

                    # Early exit if high confidence
                    if conf >= self.VERIFIED_THRESHOLD:
                        break
        except Exception as e:
            continue

    # Determine verdict
    if best_confidence >= self.VERIFIED_THRESHOLD:
        verdict = "verified" if best_confidence >= self.VERIFIED_THRESHOLD else "uncertain"
    else:
        verdict = "suspicious"

    # Re-evaluate: verified >= 0.8, uncertain 0.5-0.8
    if best_confidence >= 0.8:
        verdict = "verified"
    elif best_confidence >= 0.5:
        verdict = "uncertain"
    else:
        verdict = "suspicious"

    # Enrich if requested
    enriched_entry = None
    if enrich and best_paper:
        enriched_entry = self._enrich_entry(entry, best_paper)

    error = None
    if not best_paper and search_sources != ["all"]:
        error = "not found in specified backends"
    elif not best_paper:
        error = "not found in any backend"

    return VerificationResult(
        bib_key=bib_key,
        original_title=title,
        confidence=best_confidence,
        verdict=verdict,
        matched_paper=best_paper,
        backend_used=best_source,
        discrepancies=discrepancies,
        error=error,
        enriched_entry=enriched_entry,
    )

def _enrich_entry(self, entry: dict, paper: Paper) -> dict:
    """Enrich a BibTeX entry with metadata from the matched paper."""
    enriched = entry.copy()

    if not enriched.get("DOI") and paper.identifier:
        enriched["DOI"] = paper.identifier

    if not enriched.get("URL") and paper.url:
        enriched["URL"] = paper.url

    if not enriched.get("ABSTRACT") and paper.abstract:
        enriched["ABSTRACT"] = paper.abstract

    return enriched
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_bibtex.py::TestBibtexVerifier::test_verify_single_entry_mocked -v
```

- [ ] **Step 5: Commit**

```bash
git add paperscout/bibtex.py tests/test_bibtex.py
git commit -m "feat: implement entry verification with backend search"
```

---

## Task 8: Implement annotated BibTeX output

**Files:**
- Modify: `paperscout/bibtex.py:_write_annotated_bibtex`
- Test: `tests/test_bibtex.py::TestAnnotatedOutput`

- [ ] **Step 1: Write failing test for annotated output**

```python
# tests/test_bibtex.py - add TestAnnotatedOutput class
class TestAnnotatedOutput(unittest.TestCase):
    """Test cases for annotated BibTeX output."""

    def setUp(self):
        from paperscout.bibtex import BibtexVerifier, VerificationResult
        self.verifier = BibtexVerifier()

    def test_write_annotated_bibtex(self):
        """Test writing annotated BibTeX file."""
        import tempfile
        import os

        # Create input file
        bib_content = '''@article{test2020,
  title={Test Paper},
  author={Doe, John},
  year={2020}
}'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.bib', delete=False) as f:
            f.write(bib_content)
            input_path = f.name

        output_path = input_path + ".out"

        try:
            results = [
                VerificationResult(
                    bib_key="test2020",
                    original_title="Test Paper",
                    confidence=0.95,
                    verdict="verified",
                    matched_paper=None,
                    backend_used="arxiv",
                    discrepancies=[],
                    error=None,
                )
            ]

            self.verifier._write_annotated_bibtex(input_path, output_path, results)

            with open(output_path, 'r') as f:
                output = f.read()

            self.assertIn("% verification_status: verified", output)
            self.assertIn("% verification_score: 0.95", output)
            self.assertIn("@article{test2020", output)
        finally:
            os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_bibtex.py::TestAnnotatedOutput -v
```

- [ ] **Step 3: Implement _write_annotated_bibtex**

```python
def _write_annotated_bibtex(
    self,
    input_path: str,
    output_path: str,
    results: list[VerificationResult],
    enrich: bool = False,
) -> None:
    """
    Write an annotated BibTeX file with verification results.

    Args:
        input_path: Path to original .bib file.
        output_path: Path to output .bib file.
        results: Verification results.
        enrich: Whether to include enriched fields.
    """
    # Read original content
    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Build result lookup by key
    result_map = {r.bib_key: r for r in results}

    # Insert annotations before each entry
    lines = content.split("\n")
    output_lines = []

    for line in lines:
        # Check if this line starts a new entry
        match = re.match(r"^(@\w+)\{(\w+)", line)
        if match:
            entry_type = match.group(1)
            entry_key = match.group(2)

            # Add annotation comments
            if entry_key in result_map:
                result = result_map[entry_key]
                output_lines.append(f"% verification_status: {result.verdict}")
                output_lines.append(f"% verification_score: {result.confidence:.2f}")
                output_lines.append(f"% verification_source: {result.backend_used or 'none'}")
                if result.matched_paper:
                    output_lines.append(f"% verification_matched_title: {result.matched_paper.title}")
                if result.discrepancies:
                    output_lines.append(f"% verification_discrepancies: {', '.join(result.discrepancies)}")
                if enrich and result.enriched_entry:
                    # Would need to modify the actual entry content here
                    pass

        output_lines.append(line)

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_bibtex.py::TestAnnotatedOutput -v
```

- [ ] **Step 5: Commit**

```bash
git add paperscout/bibtex.py tests/test_bibtex.py
git commit -m "feat: implement annotated BibTeX output"
```

---

## Task 9: Implement JSON report generation

**Files:**
- Modify: `paperscout/bibtex.py:_generate_json_report`
- Test: `tests/test_bibtex.py` (add JSON test)

- [ ] **Step 1: Write failing test for JSON report**

```python
def test_generate_json_report(self):
    """Test generating JSON verification report."""
    from paperscout.bibtex import BibtexVerifier, VerificationResult
    import tempfile
    import os
    import json

    verifier = BibtexVerifier()
    results = [
        VerificationResult(
            bib_key="test2020",
            original_title="Test Paper",
            confidence=0.95,
            verdict="verified",
            matched_paper=None,
            backend_used="arxiv",
            discrepancies=[],
            error=None,
        )
    ]

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json_path = f.name

    try:
        verifier._generate_json_report(json_path, results)

        with open(json_path, 'r') as f:
            report = json.load(f)

        self.assertEqual(len(report), 1)
        self.assertEqual(report[0]["bib_key"], "test2020")
        self.assertEqual(report[0]["verdict"], "verified")
    finally:
        os.unlink(json_path)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_bibtex.py::TestAnnotatedOutput::test_generate_json_report -v
```

- [ ] **Step 3: Implement _generate_json_report**

```python
def _generate_json_report(self, path: str, results: list[VerificationResult]) -> None:
    """
    Generate a JSON verification report.

    Args:
        path: Output JSON file path.
        results: Verification results.
    """
    report = []

    for r in results:
        entry = {
            "bib_key": r.bib_key,
            "original_title": r.original_title,
            "verdict": r.verdict,
            "confidence": round(r.confidence, 3),
            "tier": r.verdict,  # Same as verdict for now
            "matched_paper": r.matched_paper.to_dict() if r.matched_paper else None,
            "backend_used": r.backend_used,
            "discrepancies": r.discrepancies,
            "error": r.error,
        }
        report.append(entry)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_bibtex.py::TestAnnotatedOutput::test_generate_json_report -v
```

- [ ] **Step 5: Commit**

```bash
git add paperscout/bibtex.py tests/test_bibtex.py
git commit -m "feat: implement JSON report generation"
```

---

## Task 10: Implement console report formatter

**Files:**
- Modify: `paperscout/bibtex.py:_format_verification_report`
- Test: Manual testing via CLI

- [ ] **Step 1: Implement _format_verification_report**

```python
def _format_verification_report(self, results: list[VerificationResult]) -> Table:
    """
    Format verification results as a Rich table.

    Args:
        results: Verification results.

    Returns:
        Rich Table.
    """
    from rich.table import Table
    from rich.text import Text

    table = Table(show_header=True, header_style="bold")
    table.add_column("Key", style="dim", width=15)
    table.add_column("Title", width=40)
    table.add_column("Conf.", justify="right", width=8)
    table.add_column("Tier", width=10)
    table.add_column("Matched", width=35)
    table.add_column("Notes", width=20)

    verified = uncertain = suspicious = errors = 0

    for r in results:
        # Count verdicts
        if r.error:
            errors += 1
        elif r.verdict == "verified":
            verified += 1
        elif r.verdict == "uncertain":
            uncertain += 1
        else:
            suspicious += 1

        # Tier emoji
        if r.error:
            tier = "⚪ Error"
        elif r.verdict == "verified":
            tier = "🟢 Verified"
        elif r.verdict == "uncertain":
            tier = "🟡 Uncertain"
        else:
            tier = "🔴 Suspicious"

        # Truncate title
        title = r.original_title[:37] + "..." if len(r.original_title) > 40 else r.original_title

        # Matched title
        matched = r.matched_paper.title[:32] + "..." if r.matched_paper and len(r.matched_paper.title) > 35 else (r.matched_paper.title if r.matched_paper else "—")

        # Notes
        notes = "; ".join(r.discrepancies[:2]) if r.discrepancies else ("Not found" if r.error and "not found" in r.error else "")

        table.add_row(
            r.bib_key,
            title,
            f"{r.confidence:.0%}" if r.confidence > 0 else "—",
            tier,
            matched,
            notes,
        )

    # Summary caption
    summary = f"Verified: {verified} | Uncertain: {uncertain} | Suspicious: {suspicious} | Errors: {errors}"
    table.caption = summary
    table.caption_style = "dim"

    return table
```

- [ ] **Step 2: Commit**

```bash
git add paperscout/bibtex.py
git commit -m "feat: implement console report formatter"
```

---

## Task 11: Add verify CLI command

**Files:**
- Modify: `paperscout/cli.py`
- Test: Manual CLI testing

- [ ] **Step 1: Add verify command to CLI**

Add after the download parser section in `main()`:

```python
# Verify command
verify_parser = subparsers.add_parser("verify", help="Verify BibTeX entries")
verify_parser.add_argument(
    "file",
    help="Path to .bib file to verify",
)
verify_parser.add_argument(
    "-s", "--source",
    dest="sources",
    help="Backends to use (comma-separated: arxiv,dblp,etc.)",
)
verify_parser.add_argument(
    "--enrich",
    action="store_true",
    help="Fill in missing fields from discovered metadata",
)
verify_parser.add_argument(
    "--threshold",
    type=float,
    default=0.5,
    help="Confidence threshold for suspicious (default: 0.5)",
)
verify_parser.add_argument(
    "--parallel",
    action="store_true",
    help="Enable parallel backend queries",
)
verify_parser.add_argument(
    "-o", "--output",
    help="Write annotated .bib to this path",
)
verify_parser.add_argument(
    "-j", "--json",
    dest="json_output",
    help="Write JSON report to this path",
)
```

Then add handler in the command dispatch:

```python
elif args.command == "verify":
    from paperscout.client import PaperFinderClient
    client = PaperFinderClient()

    sources = args.sources.split(",") if args.sources else None
    results = client.verify_bibtex(
        args.file,
        sources=sources,
        enrich=args.enrich,
        threshold=args.threshold,
        parallel=args.parallel,
    )

    # Print console report
    from paperscout.bibtex import BibtexVerifier
    verifier = BibtexVerifier()
    console.print(verifier._format_verification_report(results))

    # Write annotated .bib if requested
    if args.output:
        verifier._write_annotated_bibtex(args.file, args.output, results, enrich=args.enrich)
        console.print(f"[green]Annotated BibTeX written to {args.output}[/green]")

    # Write JSON report if requested
    if args.json_output:
        verifier._generate_json_report(args.json_output, results)
        console.print(f"[green]JSON report written to {args.json_output}[/green]")
```

- [ ] **Step 2: Test CLI manually**

```bash
pip install -e .
paperscout verify --help
```

- [ ] **Step 3: Commit**

```bash
git add paperscout/cli.py
git commit -m "feat: add verify CLI command"
```

---

## Task 12: Add --bibtex flag to search/match commands

**Files:**
- Modify: `paperscout/cli.py`
- Test: Manual CLI testing

- [ ] **Step 1: Add --bibtex flag to search and match parsers**

```python
# In search_parser and match_parser, add:
search_parser.add_argument(
    "--bibtex",
    action="store_true",
    help="Output results as BibTeX",
)
```

- [ ] **Step 2: Handle --bibtex in search command**

```python
elif args.command == "search":
    results = client.search(args.query, source=args.source, limit=args.limit)

    if args.bibtex:
        # Output as BibTeX
        bibtex_output = "\n\n".join(p.to_bibtex() for p in results)
        output_results(bibtex_output, args.output, as_json=False)
    else:
        output_results(results, args.output, args.json, show_abstract=args.abstract, show_similarity=not args.no_similarity)
```

- [ ] **Step 3: Handle --bibtex in match command**

```python
elif args.command == "match":
    results = client.search(args.query, source=args.source, limit=10)
    if results:
        best_match = results[0]
        if args.bibtex:
            output_results(best_match.to_bibtex(), args.output, as_json=False)
        else:
            output_results(best_match, args.output, args.json)
```

- [ ] **Step 4: Test CLI manually**

```bash
paperscout search "Attention Is All You Need" --bibtex
```

- [ ] **Step 5: Commit**

```bash
git add paperscout/cli.py
git commit -m "feat: add --bibtex flag to search and match commands"
```

---

## Task 13: Add verify_bibtex method to client

**Files:**
- Modify: `paperscout/client.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: Add verify_bibtex method**

```python
def verify_bibtex(
    self,
    path: str,
    sources: list[str] | None = None,
    enrich: bool = False,
    threshold: float = 0.5,
    parallel: bool = False,
) -> list:
    """
    Verify BibTeX entries in a file.

    Args:
        path: Path to .bib file.
        sources: Specific backends to use.
        enrich: Whether to enrich entries.
        threshold: Confidence threshold.
        parallel: Whether to run in parallel.

    Returns:
        List of VerificationResult objects.
    """
    from paperscout.bibtex import BibtexVerifier

    verifier = BibtexVerifier(threshold=threshold)
    return verifier.verify_file(path, sources=sources, enrich=enrich, parallel=parallel)
```

- [ ] **Step 2: Commit**

```bash
git add paperscout/client.py
git commit -m "feat: add verify_bibtex method to client"
```

---

## Task 14: Export BibtexVerifier from package

**Files:**
- Modify: `paperscout/__init__.py`

- [ ] **Step 1: Add exports**

```python
from paperscout.bibtex import BibtexVerifier, VerificationResult

__all__ = [
    "PaperFinderClient",
    "PaperSearcher",
    "BaseBackend",
    "ArxivBackend",
    "DblpBackend",
    "SemanticScholarBackend",
    "ACLAnthologyBackend",
    "Paper",
    "BibtexVerifier",
    "VerificationResult",
]
```

- [ ] **Step 2: Commit**

```bash
git add paperscout/__init__.py
git commit -m "feat: export BibtexVerifier and VerificationResult"
```

---

## Task 15: Create test fixtures

**Files:**
- Create: `tests/fixtures/sample.bib`

- [ ] **Step 1: Create sample.bib fixture**

```bibtex
@article{vaswani2017attention,
  title={Attention Is All You Need},
  author={Vaswani, Ashish and Shazeer, Noam and Parmar, Niki},
  journal={arXiv preprint arXiv:1706.03762},
  year={2017}
}

@inproceedings{devlin2019bert,
  title={BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding},
  author={Devlin, Jacob and Chang, Ming-Wei and Lee, Kenton and Toutanova, Kristina},
  booktitle={Proceedings of NAACL-HLT},
  pages={4171--4186},
  year={2019}
}

@article{fake2025quantum,
  title={Quantum NLP Revolution: Breaking All Boundaries},
  author={Smith, John and Doe, Jane},
  journal={Made Up Journal},
  year={2025}
}

@article{ambiguous2020deep,
  title={Deep Learning for Natural Language Processing},
  author={Fake, Author and Another, Person},
  year={2020}
}

@article{missing2018,
  title={A Paper With Missing Fields},
  author={Someone, Unknown}
}
```

- [ ] **Step 2: Commit**

```bash
git add tests/fixtures/sample.bib
git commit -m "feat: add sample.bib test fixture"
```

---

## Task 16: Final integration tests

**Files:**
- Modify: `tests/test_bibtex.py` (add integration tests)

- [ ] **Step 1: Add integration test**

```python
def test_full_verification_workflow(self):
    """Test full verification workflow with mocked backends."""
    from paperscout.bibtex import BibtexVerifier
    from unittest.mock import patch
    import tempfile
    import os

    # Create test .bib file
    bib_content = '''
@article{vaswani2017attention,
  title={Attention Is All You Need},
  author={Vaswani, Ashish},
  year={2017}
}
@article{fake2025quantum,
  title={Completely Fake Quantum Paper},
  author={Fake, Author},
  year={2025}
}
'''
    with tempfile.NamedTemporaryFile(mode='w', suffix='.bib', delete=False) as f:
        f.write(bib_content)
        temp_path = f.name

    try:
        verifier = BibtexVerifier()

        # Mock successful search for first, empty for second
        mock_paper = Paper(
            title="Attention Is All You Need",
            authors=["Ashish Vaswani"],
            year=2017,
            abstract=None,
            source="arxiv",
            identifier="1706.03762",
            url="",
            pdf_url=None,
            published=None,
            categories=[],
        )

        with patch.object(verifier.searcher, 'search', side_effect=[[mock_paper], []]):
            results = verifier.verify_file(temp_path)

            self.assertEqual(len(results), 2)
            self.assertEqual(results[0].verdict, "verified")
            self.assertEqual(results[1].verdict, "suspicious")
    finally:
        os.unlink(temp_path)
```

- [ ] **Step 2: Run all tests**

```bash
pytest tests/test_bibtex.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_bibtex.py
git commit -m "feat: add integration tests for BibTeX verification"
```

---

## Task 17: Update README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add documentation for new features**

Add new sections after the "Sources" table:

```markdown
## BibTeX Support

### Export Papers as BibTeX

```bash
# Search and export as BibTeX
paperscout search "Attention Is All You Need" --bibtex

# Save to file
paperscout match "Transformer" --bibtex --output citations.bib
```

```python
from paperscout import Paper

paper = Paper(...)
bibtex = paper.to_bibtex()
# or with custom key
bibtex = paper.to_bibtex(entry_key="vaswani2017")
```

### Verify BibTeX Files

Verify that papers in a BibTeX file actually exist in academic databases:

```bash
# Basic verification
paperscout verify references.bib

# With specific backends
paperscout verify references.bib --source arxiv,dblp

# Enrich entries with discovered metadata
paperscout verify references.bib --enrich

# Output annotated .bib and JSON report
paperscout verify references.bib --output verified.bib --json report.json
```

```python
from paperscout import PaperFinderClient

client = PaperFinderClient()
results = client.verify_bibtex("references.bib")

for result in results:
    print(f"{result.bib_key}: {result.verdict} ({result.confidence:.0%})")
```

The verifier outputs:
- **Console report**: Rich table showing verification status for each entry
- **Annotated .bib**: Original file with verification comments
- **JSON report**: Structured data for downstream processing
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add BibTeX verification and export documentation"
```

---

## Self-Review Checklist

1. **Spec coverage:** All sections covered? ✓ (Paper.to_bibtex, BibtexVerifier, verify command, --bibtex flag, confidence scoring, smart routing, all output formats)

2. **Placeholder scan:** Any TBD/TODO left? Need to remove TODO comment in Task 3's _parse_bibtex stub.

3. **Type consistency:** Method names match across tasks? ✓ (_smart_routing, _compute_confidence, _verify_entry, etc.)

Plan complete. Ready for execution.
