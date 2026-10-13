"""
Markdown reference parsing and grounding.

Parses the References section of a markdown paper (e.g. a PDF converted to
markdown) in the common ACL-style format::

    Author1, Author2, and Author3. Year. Title. Venue, details.

and grounds each reference field by field.
"""

from __future__ import annotations

import html
import re

from paperscout.bibtex import ground_all
from paperscout.grounding import GroundingResult, Grounder, Reference, extract_arxiv_id, extract_doi


class MarkdownRefParser:
    """Parse and ground references from markdown files."""

    # ". 2024." or ". 2024a." (space between period and year)
    YEAR_PATTERN = re.compile(r'\.\s*(\d{4})([a-z])?\.\s*')

    def __init__(self, sources: list[str] | None = None, use_cache: bool = True, grounder: Grounder | None = None):
        self._sources = sources
        self._use_cache = use_cache
        self._grounder = grounder

    @property
    def grounder(self) -> Grounder:
        if self._grounder is None:
            self._grounder = Grounder(sources=self._sources, use_cache=self._use_cache)
        return self._grounder

    def parse_file(self, path: str) -> list[dict]:
        """
        Parse references from a markdown file.

        Returns:
            List of dicts with keys 'authors', 'authors_truncated', 'year', 'title',
            'venue', 'doi', 'arxiv_id' and 'raw_text'.
        """
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(path, encoding="latin-1") as f:
                content = f.read()

        refs_section = self._find_references_section(content)
        if not refs_section:
            return []
        return self._parse_references(refs_section)

    def _find_references_section(self, content: str) -> str | None:
        lines = content.split('\n')
        refs_start = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('#') and 'reference' in stripped.lower():
                refs_start = i + 1
                break
        if refs_start is None:
            return None

        refs_end = len(lines)
        for i in range(refs_start, len(lines)):
            stripped = lines[i].strip()
            if stripped.startswith('## ') and 'reference' not in stripped.lower():
                refs_end = i
                break
        return '\n'.join(lines[refs_start:refs_end])

    def _parse_references(self, refs_content: str) -> list[dict]:
        references = []
        for entry in self._split_reference_entries(refs_content):
            entry = entry.strip()
            if not entry or len(entry) < 20:
                continue
            parsed = self._parse_single_reference(entry)
            if parsed and parsed.get('title'):
                references.append(parsed)
        return references

    def _split_reference_entries(self, refs_content: str) -> list[str]:
        """
        Split the references section into entries.

        Blank lines separate paragraphs; paragraphs without a year pattern (or that
        start with a non-year digit or a link bracket) are merged into the previous
        entry because PDF conversion often inserts spurious blank lines.
        """
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

        entries: list[str] = []
        for para in paragraphs:
            if not para:
                continue
            is_continuation = (
                not self.YEAR_PATTERN.search(para)
                or bool(re.match(r'^\d{4}', para))
                or para.startswith('[')
                or bool(re.match(r'^\d(?!\d{3})', para))
            )
            if entries and is_continuation:
                entries[-1] = entries[-1] + ' ' + para
            else:
                entries.append(para)
        return entries

    def _parse_single_reference(self, ref_text: str) -> dict | None:
        """Parse "Authors. Year. Title. Venue, details." into fields."""
        text = html.unescape(ref_text.strip())
        urls = ' '.join(re.findall(r'\]\(([^)]+)\)', text))
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        text = text.lstrip('[').rstrip(']')

        year_match = self.YEAR_PATTERN.search(text)
        if not year_match:
            return None

        authors_part = text[:year_match.start()]
        rest = text[year_match.end():]
        title = self._extract_title(rest)
        if not title:
            return None
        venue = self._extract_venue(rest[rest.find(title) + len(title):] if title in rest else "")

        return {
            'authors': self._parse_authors(authors_part),
            'authors_truncated': bool(re.search(r'\bet\s+al\b|\bothers\b', authors_part, re.IGNORECASE)),
            'year': int(year_match.group(1)),
            'title': title,
            'venue': venue,
            'doi': extract_doi(text, urls),
            'arxiv_id': extract_arxiv_id(text, urls),
            'raw_text': ref_text,
        }

    def _extract_title(self, text: str) -> str:
        """Title = text after the year up to the first venue/source indicator."""
        text = text.strip()
        terminators = [
            r'\s+In\s+(?:Proceedings|Advances|Findings|the\s|\d+)',
            r'\s+Preprint',
            r'\s+Transactions\s+of',
            r'\s+Journal',
            r'\s+IEEE',
            r'\s+ACM',
            r'\s+arXiv',
            r'\s+https?://',
            r'\s+Accessed:',
            r'\s*\(URL',
            r'\s+In\s+print',
            r'\.\s*Technical\s+[Rr]eport',
            r'\.\s*\n',
        ]
        earliest_pos = len(text)
        for terminator in terminators:
            match = re.search(terminator, text, re.IGNORECASE)
            if match and match.start() < earliest_pos:
                earliest_pos = match.start()
        return text[:earliest_pos].strip().rstrip('.,;:')

    @staticmethod
    def _extract_venue(text: str) -> str:
        """Venue = remainder after the title, without "In", pages, URLs and publisher."""
        s = re.sub(r'https?://\S+', '', text).strip().lstrip('.').strip()
        s = re.sub(r'^In\s+', '', s)
        s = re.sub(r',?\s*pages?\s+[\d\u2013\-–]+.*$', '', s, flags=re.IGNORECASE)
        s = re.split(r',\s*(?:Online|[A-Z][a-z]+,\s+[A-Z])', s)[0]
        return s.strip().rstrip('.,;: ')

    def _parse_authors(self, authors_str: str) -> list[str]:
        """Split "A, B, and C" into names, dropping "and N others" / "et al."."""
        authors_str = authors_str.strip().rstrip('.')
        authors_str = re.sub(r',?\s+and\s+\d+\s+others\.?', '', authors_str, flags=re.IGNORECASE)
        authors_str = re.sub(r',?\s+(?:et\s+al\.?|and\s+others)\.?$', '', authors_str, flags=re.IGNORECASE)
        authors_str = re.sub(r',?\s+and\s+', ', ', authors_str, flags=re.IGNORECASE)
        return [p.strip() for p in authors_str.split(',') if p.strip() and len(p.strip()) > 1]

    @staticmethod
    def to_reference(parsed: dict) -> Reference:
        return Reference(
            title=parsed['title'],
            authors=parsed['authors'],
            authors_truncated=parsed.get('authors_truncated', False),
            year=parsed.get('year'),
            venue=parsed.get('venue', ''),
            doi=parsed.get('doi', ''),
            arxiv_id=parsed.get('arxiv_id', ''),
            raw=parsed.get('raw_text', ''),
        )

    def verify_file(self, path: str, workers: int = 1) -> list[GroundingResult]:
        """Parse and ground every reference in the markdown file."""
        refs = [self.to_reference(p) for p in self.parse_file(path)]
        if not refs:
            return []
        return ground_all(self.grounder, refs, "Verifying markdown references", workers)
