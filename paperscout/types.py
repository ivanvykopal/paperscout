"""
Standardized types for paperscout.

This module defines the core data types used throughout the paperscout package.
"""

from dataclasses import dataclass
from typing import List, Optional


def _infer_entry_type(source: str, categories: List[str] | None = None) -> str:
    """Infer BibTeX entry type from source."""
    if source == "acl_anthology":
        return "inproceedings"
    elif source == "dblp":
        return "inproceedings"
    elif source == "semantic_scholar":
        # Check venue for clues
        if categories and any(
            v.lower() in "acl emnlp naacl iclr" for v in categories
        ):
            return "inproceedings"
        return "article"
    else:  # arxiv default
        return "article"


def _generate_citation_key(authors: List[str], year: int | None, title: str) -> str:
    """Generate a citation key from author, year, and title."""
    STOP_WORDS = {
        "a",
        "an",
        "the",
        "on",
        "in",
        "of",
        "for",
        "to",
        "and",
        "with",
        "from",
        "by",
    }

    # Get first author's last name
    if authors:
        first_author = authors[0]
        parts = first_author.strip().split()
        last_name = parts[-1].lower() if parts else ""
    else:
        last_name = ""

    # Get significant word from title
    title_words = title.lower().split()
    significant_words = [w for w in title_words if w not in STOP_WORDS and len(w) > 2]
    significant_word = significant_words[0] if significant_words else ""

    # Combine into key
    key_parts = [
        p
        for p in [last_name, str(year) if year else "", significant_word]
        if p
    ]
    key = "".join(key_parts[:3])  # Limit to 3 parts

    # Sanitize: only alphanumeric
    key = "".join(c for c in key if c.isalnum()).lower()
    return key or "unknown"


@dataclass
class Paper:
    """
    Standardized representation of a paper returned by all backend _format_result functions.

    Attributes:
        title: The title of the paper.
        authors: List of authors.
        year: Publication year (optional).
        abstract: Paper abstract (optional).
        source: Source database name (e.g., 'arxiv', 'dblp', 'acl_anthology', 'semantic_scholar').
        identifier: Unique identifier from the source (e.g., arXiv ID, DOI, DBLP key).
        url: URL to the paper's abstract page.
        pdf_url: URL to the PDF (optional).
        published: Publication date as string (optional).
        categories: List of categories or tags (optional).
        similarity: Relevance score calculated during search (optional).
    """

    title: str
    authors: List[str]
    year: Optional[int]
    abstract: Optional[str]
    source: str
    identifier: str
    url: str
    pdf_url: Optional[str]
    published: Optional[str]
    categories: List[str]
    similarity: Optional[float] = None

    def to_dict(self) -> dict:
        """Convert Paper to a dictionary."""
        return {
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "abstract": self.abstract,
            "source": self.source,
            "identifier": self.identifier,
            "url": self.url,
            "pdf_url": self.pdf_url,
            "published": self.published,
            "categories": self.categories,
            "similarity": self.similarity,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Paper":
        """
        Create a Paper instance from a dictionary.

        Args:
            data: Dictionary with paper data.

        Returns:
            Paper instance.
        """
        return cls(
            title=data.get("title", ""),
            authors=data.get("authors", []),
            year=data.get("year"),
            abstract=data.get("abstract"),
            source=data.get("source", ""),
            identifier=data.get("identifier", ""),
            url=data.get("url", ""),
            pdf_url=data.get("pdf_url"),
            published=data.get("published"),
            categories=data.get("categories", []),
            similarity=data.get("similarity"),
        )

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
            entry_type = _infer_entry_type(self.source, self.categories)

        # Generate or use provided citation key
        if entry_key is None:
            entry_key = _generate_citation_key(self.authors, self.year, self.title)

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
