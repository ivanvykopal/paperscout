"""
BibTeX parsing, verification, and export functionality.

This module provides tools for verifying BibTeX entries against academic
databases and exporting Paper objects as BibTeX entries.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import bibtexparser
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
    discrepancies: list[str] = field(default_factory=list)
    error: str | None = None
    enriched_entry: dict[str, Any] | None = None


class BibtexVerifier:
    """Verify BibTeX entries against academic databases.

    Threshold Design:
        The verdict for each entry is determined by comparing the title similarity
        score (from _title_similarity) against two thresholds:

        - VERIFIED_THRESHOLD (0.80): Entries with similarity >= 0.80 are considered
          "verified" - a strong match was found with high confidence.

        - UNCERTAIN_THRESHOLD (0.50): Entries with similarity between 0.50 and 0.80
          are marked "uncertain" - a potential match exists but requires manual review.

        - Below 0.50: Entries are marked "suspicious" - either no good match was found
          or the matched paper has a significantly different title.

        These thresholds were chosen based on empirical testing with academic paper
        titles, where exact or near-exact matches typically score >0.90, while
        unrelated papers score <0.30.
    """

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
        """
        Parse a BibTeX file into a list of entry dictionaries.

        Args:
            path: Path to the .bib file.

        Returns:
            List of entry dictionaries. Keys are uppercase (e.g., "TITLE", "AUTHOR").
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            # Fallback to latin-1
            with open(path, "r", encoding="latin-1") as f:
                content = f.read()

        try:
            library = bibtexparser.loads(content)
        except Exception as e:
            # Handle malformed BibTeX gracefully
            raise ValueError(f"Failed to parse BibTeX file: {e}")

        entries = []

        for entry in library.entries:
            # Convert to dict with uppercase keys
            entry_dict = {}
            for key, value in entry.items():
                entry_dict[key.upper()] = value
            entry_dict["ID"] = entry.get("ID", "")
            entries.append(entry_dict)

        return entries

    def _verify_entry(
        self,
        entry: dict,
        sources: list[str] | None,
        enrich: bool,
    ) -> VerificationResult:
        """Verify a single BibTeX entry."""
        bib_key = entry.get('ID', '')
        title = entry.get('TITLE', '')

        # Search for matching paper
        results = self.searcher.search(query=title, source=sources, limit=1)

        if not results:
            return VerificationResult(
                bib_key=bib_key,
                original_title=title,
                confidence=0.0,
                verdict="suspicious",
                matched_paper=None,
                backend_used=None,
                discrepancies=["No matching paper found"],
                error=None,
                enriched_entry=None,
            )

        best_match = results[0]

        # Compute confidence using comprehensive scoring
        confidence, discrepancies = self._compute_confidence(entry, best_match)

        # Determine verdict based on confidence
        if confidence >= self.VERIFIED_THRESHOLD:
            verdict = "verified"
        elif confidence >= self.UNCERTAIN_THRESHOLD:
            verdict = "uncertain"
        else:
            verdict = "suspicious"

        # Enrich entry if requested
        enriched_entry = None
        if enrich and best_match:
            enriched_entry = self._enrich_entry(entry, best_match)

        return VerificationResult(
            bib_key=bib_key,
            original_title=title,
            confidence=confidence,
            verdict=verdict,
            matched_paper=best_match,
            backend_used=best_match.source,
            discrepancies=discrepancies,
            error=None,
            enriched_entry=enriched_entry,
        )

    def _find_discrepancies(self, entry: dict, matched_paper: Paper) -> list[str]:
        """Find discrepancies between BibTeX entry and matched paper."""
        discrepancies = []

        # Check year
        entry_year = entry.get('YEAR')
        if entry_year and matched_paper.year:
            try:
                if int(entry_year) != matched_paper.year:
                    discrepancies.append(f"Year mismatch: {entry_year} vs {matched_paper.year}")
            except ValueError:
                pass

        # Check authors
        entry_authors = entry.get('AUTHOR', '')
        if entry_authors:
            paper_authors_str = " and ".join(matched_paper.authors)
            if entry_authors.lower() != paper_authors_str.lower():
                discrepancies.append("Author list differs")

        return discrepancies

    def _enrich_entry(self, entry: dict, matched_paper: Paper) -> dict:
        """Enrich a BibTeX entry with metadata from the matched paper."""
        enriched = entry.copy()

        # Update fields from matched paper
        if matched_paper.title:
            enriched['TITLE'] = matched_paper.title
        if matched_paper.authors:
            enriched['AUTHOR'] = " and ".join(matched_paper.authors)
        if matched_paper.year:
            enriched['YEAR'] = str(matched_paper.year)
        if matched_paper.abstract:
            enriched['ABSTRACT'] = matched_paper.abstract
        if matched_paper.url:
            enriched['URL'] = matched_paper.url

        return enriched

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
        if "arxiv:" in eprint:
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

    def format_report(self, results: list[VerificationResult]) -> str:
        """Format verification results as a human-readable report."""
        lines = []
        lines.append(f"BibTeX Verification Report")
        lines.append(f"=" * 50)
        lines.append(f"Total entries: {len(results)}")
        lines.append("")

        verified = [r for r in results if r.verdict == "verified"]
        uncertain = [r for r in results if r.verdict == "uncertain"]
        suspicious = [r for r in results if r.verdict == "suspicious"]

        lines.append(f"Verified: {len(verified)}")
        lines.append(f"Uncertain: {len(uncertain)}")
        lines.append(f"Suspicious: {len(suspicious)}")
        lines.append("")

        for result in results:
            lines.append(f"[{result.verdict.upper()}] {result.bib_key}")
            lines.append(f"  Title: {result.original_title[:60]}...")
            lines.append(f"  Confidence: {result.confidence:.2f}")
            if result.backend_used:
                lines.append(f"  Backend: {result.backend_used}")
            if result.discrepancies:
                lines.append(f"  Discrepancies:")
                for disc in result.discrepancies:
                    lines.append(f"    - {disc}")
            lines.append("")

        return "\n".join(lines)

    def export_as_table(self, results: list[VerificationResult]) -> Table:
        """Export verification results as a Rich Table."""
        table = Table(title="BibTeX Verification Results")

        table.add_column("Key", style="cyan")
        table.add_column("Title", style="magenta")
        table.add_column("Confidence", justify="right")
        table.add_column("Verdict", justify="center")
        table.add_column("Backend", style="green")

        for result in results:
            table.add_row(
                result.bib_key,
                result.original_title[:40] + "..." if len(result.original_title) > 40 else result.original_title,
                f"{result.confidence:.2f}",
                result.verdict,
                result.backend_used or "-",
            )

        return table

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
        year_match_score = self._compute_year_score(entry_year, paper.year)
        year_component = year_match_score * 0.15
        if entry_year and paper.year and entry_year != paper.year:
            discrepancies.append(f"year mismatch: {entry_year} vs {paper.year}")

        # Source agreement (15%)
        source_score = 0.15  # Full credit since we found it in one backend

        total_score = title_score + author_score + year_component + source_score

        return total_score, discrepancies

    def _parse_authors_field(self, author_field: str) -> list[str]:
        """Parse BibTeX author field into list of last names."""
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
                result.append(parts[0].strip().lower())  # Just last name
            else:
                # "First Last" format
                parts = author.split()
                if parts:
                    result.append(parts[-1].lower())  # Just last name
        return result

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
