"""
Markdown reference parsing, verification, and export functionality.

This module provides tools for verifying references from markdown files
(typically the References section) against academic databases.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from paperscout.types import Paper

from rich.progress import Progress
from rich.table import Table

from paperscout.bibtex import BibtexVerifier
from paperscout.similarity import _title_similarity


@dataclass
class ReferenceVerificationResult:
    """Result of verifying a single markdown reference."""

    citation_text: str  # Original citation text from markdown
    extracted_title: str
    extracted_authors: list[str]
    extracted_year: int | None
    confidence: float
    verdict: str  # "verified", "uncertain", "suspicious"
    matched_paper: Paper | None
    backend_used: str | None
    discrepancies: list[str] = field(default_factory=list)
    error: str | None = None


class MarkdownRefParser:
    """Parse and verify references from markdown files.

    This parser handles academic reference formats commonly found in
    markdown papers (e.g., ACL format):

        Author1, Author2, and Author3. Year. Title. Venue/Journal, details.
    """

    # Regex patterns for parsing references
    # Pattern for year: ". 2024." or ". 2024a." (space between period and year)
    YEAR_PATTERN = re.compile(r'\.\s*(\d{4})([a-z])?\.\s*')

    # Pattern for title (everything until next major punctuation or venue indicator)
    TITLE_PATTERN = re.compile(
        r'^([^.]+(?:\.[^.]+)*?)'
        r'\s*\.\s*(?:In\s+|Proceedings|Preprint|Journal|IEEE|ACM|arXiv|https?://|$)',
        re.IGNORECASE
    )

    def __init__(self):
        """Initialize the markdown reference parser."""
        self.verifier = BibtexVerifier()

    def parse_file(self, path: str) -> list[dict]:
        """
        Parse references from a markdown file.

        Args:
            path: Path to the markdown file.

        Returns:
            List of parsed reference dictionaries with keys:
            - 'authors': List of author names
            - 'year': Publication year (int or None)
            - 'title': Paper title
            - 'venue': Venue/journal name (optional)
            - 'raw_text': Original citation text
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="latin-1") as f:
                content = f.read()

        # Find the References section
        refs_section = self._find_references_section(content)
        if not refs_section:
            return []

        # Parse individual references
        references = self._parse_references(refs_section)
        return references

    def _find_references_section(self, content: str) -> str | None:
        """
        Find the References section in markdown content.

        Args:
            content: Full markdown content.

        Returns:
            Content of the References section, or None if not found.
        """
        # Look for ## References or # References header
        lines = content.split('\n')
        refs_start = None

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('#') and 'reference' in stripped.lower():
                refs_start = i + 1
                break

        if refs_start is None:
            return None

        # Find the next section (another ## header) or end of file
        refs_end = len(lines)
        for i in range(refs_start, len(lines)):
            stripped = lines[i].strip()
            if stripped.startswith('## ') and 'reference' not in stripped.lower():
                refs_end = i
                break

        return '\n'.join(lines[refs_start:refs_end])

    def _parse_references(self, refs_content: str) -> list[dict]:
        """
        Parse individual references from the references section.

        Args:
            refs_content: Content of the references section.

        Returns:
            List of parsed reference dictionaries.
        """
        references = []

        # Split by double newlines (paragraph separator)
        # But handle multi-line references properly
        raw_entries = self._split_reference_entries(refs_content)

        for entry in raw_entries:
            entry = entry.strip()
            if not entry or len(entry) < 20:  # Skip very short entries
                continue

            parsed = self._parse_single_reference(entry)
            if parsed and parsed.get('title'):
                references.append(parsed)

        return references

    def _split_reference_entries(self, refs_content: str) -> list[str]:
        """
        Split references section into individual entries.

        Uses paragraph-based splitting: blank lines separate paragraphs, but
        paragraphs that lack a year pattern are merged into the previous entry
        (PDF conversion often introduces spurious blank lines mid-reference).
        """
        # Collect paragraphs (groups of non-empty lines)
        paragraphs: list[str] = []
        current: list[str] = []
        for line in refs_content.split('\n'):
            stripped = line.strip()
            if not stripped:
                if current:
                    paragraphs.append(' '.join(current))
                    current = []
            else:
                current.append(stripped)
        if current:
            paragraphs.append(' '.join(current))

        # Merge continuation paragraphs into the preceding entry.
        # A paragraph is a continuation when it lacks a year OR when it starts
        # with a digit that is not a 4-digit year (e.g. "5 Team, ...") or a
        # markdown link bracket.
        entries: list[str] = []
        for para in paragraphs:
            if not para:
                continue
            has_year = bool(self.YEAR_PATTERN.search(para))
            is_year_start = bool(re.match(r'^\d{4}', para))
            starts_with_bracket = para.startswith('[')
            starts_with_non_year_digit = bool(re.match(r'^\d(?!\d{3})', para))

            is_continuation = (
                not has_year
                or is_year_start
                or starts_with_bracket
                or starts_with_non_year_digit
            )

            if entries and is_continuation:
                entries[-1] = entries[-1] + ' ' + para
            else:
                entries.append(para)

        return entries

    def _parse_single_reference(self, ref_text: str) -> dict | None:
        """
        Parse a single reference entry.

        Format: Authors. Year. Title. Venue, details.

        Args:
            ref_text: Raw reference text.

        Returns:
            Dictionary with parsed fields, or None if parsing fails.
        """
        result = {
            'authors': [],
            'year': None,
            'title': '',
            'venue': '',
            'raw_text': ref_text
        }

        # Decode HTML entities (&amp; → &) and strip markdown link syntax
        text = html.unescape(ref_text.strip())
        # Strip markdown hyperlinks: [text](url) → text, or leading [
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        text = text.lstrip('[').rstrip(']')

        # Find the year pattern - it's typically ". YYYY." in the text
        year_match = self.YEAR_PATTERN.search(text)
        if year_match:
            result['year'] = int(year_match.group(1))
            # Everything before the year is authors
            authors_part = text[:year_match.start()]
            # Everything after the year is title + venue
            rest = text[year_match.end():]
            result['authors'] = self._parse_authors(authors_part)
            # Extract title from rest
            result['title'] = self._extract_title(rest)
        else:
            # No year found - try to extract what we can
            # This is a fallback for malformed references
            return None

        return result if result['title'] else None

    def _extract_title(self, text: str) -> str:
        """
        Extract title from text after the year.

        The title typically ends before venue indicators like "In ", "Proceedings", etc.

        Args:
            text: Text after the year.

        Returns:
            Extracted title.
        """
        text = text.strip()

        # Look for common terminators that indicate end of title.
        # Each pattern matches the start of a venue/source indicator.
        # NOTE: keep "\s+In\s+" specific — a bare "in" is a common preposition.
        terminators = [
            r'\s+In\s+(?:Proceedings|Advances|Findings|the\s|\d+)',  # "In Proceedings/Advances/..."
            r'\s+Preprint',        # "Preprint, arXiv..."
            r'\s+Transactions\s+of',  # "Transactions of the ACL..."
            r'\s+Journal',         # "Journal of..."
            r'\s+IEEE',            # "IEEE..."
            r'\s+ACM',             # "ACM..."
            r'\s+arXiv',           # "arXiv:..."
            r'\s+https?://',       # URL
            r'\s+Accessed:',       # Access date
            r'\s*\(URL',           # URL withheld
            r'\s+In\s+print',      # "In print"
            r'\.\s*Technical\s+[Rr]eport',  # ". Technical report, IBM"
            r'\.\s*\n',            # Newline after period
        ]

        # Find the earliest terminator
        earliest_pos = len(text)
        for terminator in terminators:
            match = re.search(terminator, text, re.IGNORECASE)
            if match and match.start() < earliest_pos:
                earliest_pos = match.start()

        title = text[:earliest_pos].strip()
        # Remove trailing punctuation
        title = title.rstrip('.,;:')
        return title

        # Extract title (look for common terminators)
        title_terminators = [
            r'\.\s*In\s+',      # "In Proceedings..."
            r'\.\s*Preprint',   # "Preprint, arXiv..."
            r'\.\s*Journal',    # "Journal..."
            r'\.\s*IEEE',       # "IEEE..."
            r'\.\s*ACM',        # "ACM..."
            r'\.\s*arXiv',      # "arXiv..."
            r'\.\s*https?://',  # URL
            r'\.\s*Accessed:',  # Access date
            r'\.\s*\(URL',      # URL withheld
            r'\.\s*In print',   # In print
            r'\.$',             # End of sentence
        ]

        title_pattern = r'^(.+?)\s*' + '|'.join(f'(?:{t})' for t in title_terminators)
        title_match = re.match(title_pattern, text, re.IGNORECASE)

        if title_match:
            result['title'] = title_match.group(1).strip()
            # Remove trailing punctuation
            result['title'] = result['title'].rstrip('.,;:')

        return result if result['title'] else None

    def _parse_authors(self, authors_str: str) -> list[str]:
        """
        Parse author string into list of names.

        Handles formats like:
        - "John Doe, Jane Smith, and Bob Johnson"
        - "Doe, John and Smith, Jane"

        Args:
            authors_str: Raw author string.

        Returns:
            List of author names.
        """
        # Clean up the authors string
        authors_str = authors_str.strip().rstrip('.')

        # Handle "and 20 others" type patterns
        authors_str = re.sub(r',?\s+and\s+\d+\s+others\.?', '', authors_str, flags=re.IGNORECASE)

        # Replace " and " with a comma so we can split uniformly
        authors_str = re.sub(r',?\s+and\s+', ', ', authors_str, flags=re.IGNORECASE)

        # Split by comma
        parts = authors_str.split(',')

        cleaned_authors = []
        for part in parts:
            part = part.strip()
            if part and len(part) > 1:
                cleaned_authors.append(part)

        return cleaned_authors

    def verify_file(
        self,
        path: str,
        sources: list[str] | None = None,
        parallel: bool = False,
    ) -> list[ReferenceVerificationResult]:
        """
        Verify all references in a markdown file.

        Args:
            path: Path to the markdown file.
            sources: Specific backends to use (None = smart routing).
            parallel: Whether to run backend queries in parallel.

        Returns:
            List of ReferenceVerificationResult objects.
        """
        references = self.parse_file(path)

        if not references:
            return []

        results = []
        with Progress() as progress:
            task = progress.add_task(
                "[cyan]Verifying markdown references...", total=len(references)
            )
            for ref in references:
                result = self._verify_reference(ref, sources)
                results.append(result)
                progress.advance(task)

        return results

    def _verify_reference(
        self,
        reference: dict,
        sources: list[str] | None,
    ) -> ReferenceVerificationResult:
        """
        Verify a single reference.

        Args:
            reference: Parsed reference dictionary.
            sources: Specific backends to use.

        Returns:
            ReferenceVerificationResult.
        """
        title = reference.get('title', '')
        authors = reference.get('authors', [])
        year = reference.get('year')
        raw_text = reference.get('raw_text', '')

        if not title:
            return ReferenceVerificationResult(
                citation_text=raw_text,
                extracted_title='',
                extracted_authors=authors,
                extracted_year=year,
                confidence=0.0,
                verdict="suspicious",
                matched_paper=None,
                backend_used=None,
                discrepancies=["no title"],
                error="Reference has no extractable title",
            )

        # Build search query from title and authors
        query_parts = [title]
        if authors:
            # Add first author to query
            query_parts.insert(0, authors[0])
        query = ' '.join(query_parts)

        # Search for the paper
        best_paper = None
        best_source = None
        best_confidence = 0.0
        discrepancies = []

        search_sources = sources if sources else ["all"]

        for source in search_sources:
            try:
                papers = self.verifier.searcher.search(query, source=source, limit=5)
                if not papers:
                    continue

                # Find best match
                for paper in papers:
                    conf, disc = self._compute_confidence(reference, paper)
                    if conf > best_confidence:
                        best_confidence = conf
                        best_paper = paper
                        best_source = source
                        discrepancies = disc

                        # Early exit if high confidence
                        if conf >= BibtexVerifier.VERIFIED_THRESHOLD:
                            break
            except Exception:
                continue

        # Determine verdict
        if best_confidence >= BibtexVerifier.VERIFIED_THRESHOLD:
            verdict = "verified"
        elif best_confidence >= BibtexVerifier.UNCERTAIN_THRESHOLD:
            verdict = "uncertain"
        else:
            verdict = "suspicious"

        error = None
        if not best_paper:
            error = "not found in any backend"

        return ReferenceVerificationResult(
            citation_text=raw_text,
            extracted_title=title,
            extracted_authors=authors,
            extracted_year=year,
            confidence=best_confidence,
            verdict=verdict,
            matched_paper=best_paper,
            backend_used=best_source,
            discrepancies=discrepancies,
            error=error,
        )

    def _compute_confidence(
        self,
        reference: dict,
        paper: "Paper",
    ) -> tuple[float, list[str]]:
        """
        Compute confidence score for matching a reference to a paper.

        Args:
            reference: Parsed reference dictionary.
            paper: Matched Paper object.

        Returns:
            Tuple of (confidence_score, list_of_discrepancies).
        """
        discrepancies = []

        # Title similarity (50%)
        ref_title = reference.get('title', '')
        title_sim = _title_similarity(ref_title, paper.title)
        title_score = title_sim * 0.50

        # Author overlap (30%)
        ref_authors = reference.get('authors', [])
        author_overlap = self.verifier._compute_author_overlap(ref_authors, paper.authors)
        author_score = author_overlap * 0.30
        if author_overlap < 0.5 and ref_authors:
            discrepancies.append("low author overlap")

        # Year match (20%)
        ref_year = reference.get('year')
        year_match_score = self.verifier._compute_year_score(ref_year, paper.year)
        year_component = year_match_score * 0.20
        if ref_year and paper.year and ref_year != paper.year:
            discrepancies.append(f"year mismatch: {ref_year} vs {paper.year}")

        total_score = title_score + author_score + year_component

        return total_score, discrepancies

    def format_report(self, results: list[ReferenceVerificationResult]) -> str:
        """Format verification results as a human-readable report."""
        lines = []
        lines.append(f"Markdown References Verification Report")
        lines.append(f"=" * 50)
        lines.append(f"Total references: {len(results)}")
        lines.append("")

        verified = [r for r in results if r.verdict == "verified"]
        uncertain = [r for r in results if r.verdict == "uncertain"]
        suspicious = [r for r in results if r.verdict == "suspicious"]

        lines.append(f"Verified: {len(verified)}")
        lines.append(f"Uncertain: {len(uncertain)}")
        lines.append(f"Suspicious: {len(suspicious)}")
        lines.append("")

        for result in results:
            lines.append(f"[{result.verdict.upper()}] {result.extracted_title[:60]}...")
            if result.extracted_authors:
                lines.append(f"  Authors: {', '.join(result.extracted_authors[:3])}")
            if result.extracted_year:
                lines.append(f"  Year: {result.extracted_year}")
            lines.append(f"  Confidence: {result.confidence:.2f}")
            if result.backend_used:
                lines.append(f"  Backend: {result.backend_used}")
            if result.discrepancies:
                lines.append(f"  Discrepancies: {'; '.join(result.discrepancies)}")
            lines.append("")

        return "\n".join(lines)

    def _format_verification_report(
        self,
        results: list[ReferenceVerificationResult],
    ) -> Table:
        """
        Format verification results as a Rich table.

        Args:
            results: Verification results.

        Returns:
            Rich Table.
        """
        table = Table(show_header=True, header_style="bold")
        table.add_column("Title", width=45)
        table.add_column("Authors", width=25)
        table.add_column("Conf.", justify="right", width=8)
        table.add_column("Tier", width=10)
        table.add_column("Matched", width=35)

        verified = uncertain = suspicious = 0

        for r in results:
            # Count verdicts
            if r.verdict == "verified":
                verified += 1
            elif r.verdict == "uncertain":
                uncertain += 1
            else:
                suspicious += 1

            # Tier emoji
            if r.verdict == "verified":
                tier = "🟢 Verified"
            elif r.verdict == "uncertain":
                tier = "🟡 Uncertain"
            else:
                tier = "🔴 Suspicious"

            # Truncate title
            title = r.extracted_title[:42] + "..." if len(r.extracted_title) > 45 else r.extracted_title

            # Authors (first author only for display)
            authors = r.extracted_authors[0][:22] + "..." if r.extracted_authors and len(r.extracted_authors[0]) > 25 else (r.extracted_authors[0] if r.extracted_authors else "—")

            # Matched title
            matched = (
                r.matched_paper.title[:32] + "..."
                if r.matched_paper and len(r.matched_paper.title) > 35
                else (r.matched_paper.title if r.matched_paper else "—")
            )

            table.add_row(
                title,
                authors,
                f"{r.confidence:.0%}" if r.confidence > 0 else "—",
                tier,
                matched,
            )

        # Summary caption
        summary = f"Verified: {verified} | Uncertain: {uncertain} | Suspicious: {suspicious}"
        table.caption = summary
        table.caption_style = "dim"

        return table

    def export_as_table(
        self,
        results: list[ReferenceVerificationResult],
    ) -> Table:
        """Export verification results as a Rich Table."""
        table = Table(title="Markdown References Verification Results")

        table.add_column("Title", style="magenta")
        table.add_column("Authors", style="cyan")
        table.add_column("Year", justify="center")
        table.add_column("Confidence", justify="right")
        table.add_column("Verdict", justify="center")
        table.add_column("Backend", style="green")

        for result in results:
            table.add_row(
                result.extracted_title[:35] + "..." if len(result.extracted_title) > 38 else result.extracted_title,
                ', '.join(result.extracted_authors[:2])[:25] + "..." if result.extracted_authors and len(', '.join(result.extracted_authors[:2])) > 28 else (', '.join(result.extracted_authors[:2]) if result.extracted_authors else "-"),
                str(result.extracted_year) if result.extracted_year else "-",
                f"{result.confidence:.2f}",
                result.verdict,
                result.backend_used or "-",
            )

        return table
