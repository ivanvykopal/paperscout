"""
Standardized types for paperscout.

This module defines the core data types used throughout the paperscout package.
"""

from dataclasses import dataclass
from typing import List, Optional


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
