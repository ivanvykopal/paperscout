"""
ACL Anthology backend using the acl-anthology package.

ACL Anthology is the premier repository of computational linguistics
papers, covering venues like ACL, EMNLP, NAACL, and more.
"""

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from paperscout.backends.base import BaseBackend
from paperscout.similarity import _title_similarity
from paperscout.types import Paper

try:
    from acl_anthology import Anthology
    ACL_ANTHOLOGY_AVAILABLE = True
except ImportError:
    ACL_ANTHOLOGY_AVAILABLE = False


class ACLAnthologyBackend(BaseBackend):
    """
    Backend for searching and downloading papers from ACL Anthology.

    Uses the acl-anthology library for ACL Anthology API interactions.
    """

    name: str = "acl_anthology"
    supported_sources: List[str] = ["acl_anthology", "acl", "anthology"]

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the ACL Anthology backend.

        Args:
            api_key: Optional API key (not typically required for ACL Anthology).
        """
        super().__init__(api_key)
        self.client = Anthology.from_repo()
        self.download_dir = Path(tempfile.gettempdir()) / "paperscout" / "acl_anthology"
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def search(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Paper]:
        """
        Search for papers in ACL Anthology.

        Args:
            query: Search query string (paper title).
            limit: Maximum number of results to return.

        Returns:
            List of Paper objects.
        """
        if not ACL_ANTHOLOGY_AVAILABLE:
            raise ImportError(
                "acl-anthology is not installed. Install it with: pip install acl-anthology"
            )

        # Search by iterating through all papers and filtering by title
        results = self._search(query, limit=limit)

        return [self._format_result(paper, similarity) for paper, similarity in results]

    def _search(self, query: str, limit: int = 10) -> List[Tuple[Any, float]]:
        """
        Search ACL Anthology papers by title or abstract.

        Since acl-anthology doesn't have native search, we iterate through all papers
        and filter by title similarity or abstract keyword match.

        Args:
            query: Search query string (title or abstract keyword).
            limit: Maximum number of results to return.

        Returns:
            List of (paper, similarity) tuples sorted by relevance.
        """
        # Collect papers that match the query
        matching_papers = []

        # Iterate through all papers in the anthology
        for paper in self.client.papers():
            paper_title = str(getattr(paper, 'title', ''))
            paper_abstract = str(getattr(paper, 'abstract', ''))

            query_lower = query.lower()
            title_lower = paper_title.lower()
            abstract_lower = paper_abstract.lower()

            similarity = 0.0

            # Check for exact or partial match in title
            if query_lower in title_lower or title_lower in query_lower:
                similarity = 1.0
            # Check for abstract keyword match
            elif query_lower in abstract_lower:
                similarity = 0.8
            else:
                # Calculate title similarity for proximity matching
                similarity = _title_similarity(query, paper_title)

            if similarity > 0.0:  # Include all matches
                matching_papers.append((paper, similarity))

        # Sort by similarity (highest first)
        matching_papers.sort(key=lambda x: x[1], reverse=True)

        # Return top results with similarity scores
        return matching_papers[:limit]

    def download(self, identifier: str, **kwargs) -> Dict:
        """
        Download a paper from ACL Anthology.

        Args:
            identifier: ACL Anthology paper ID (e.g., 'P18-1001').
            **kwargs:
                - output_dir: Directory to save the PDF.

        Returns:
            Dictionary with download information including path.
        """
        output_dir = kwargs.get("output_dir", str(self.download_dir))
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        if not ACL_ANTHOLOGY_AVAILABLE:
            raise ImportError(
                "acl-anthology is not installed. Install it with: pip install acl-anthology"
            )

        # Get paper by ID
        try:
            paper = self.client.get(identifier)
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to retrieve paper {identifier}: {str(e)}",
            }

        if not paper:
            return {
                "status": "error",
                "message": f"Paper with ID {identifier} not found in ACL Anthology.",
            }

        # Download PDF
        pdf_url = paper.pdf
        if not pdf_url:
            return {
                "status": "error",
                "message": f"No PDF URL found for paper {identifier}.",
            }

        path, filename = self._download_file(pdf_url, identifier)

        return {
            "status": "success",
            "identifier": identifier,
            "path": path,
            "filename": filename,
            "title": paper.title if hasattr(paper, 'title') else "",
            "authors": paper.authors if hasattr(paper, 'authors') else [],
        }

    def _format_result(self, paper: Any, similarity: float = 0.0) -> Paper:
        """
        Format ACL Anthology paper to standard format.

        Args:
            paper: Raw paper object from acl-anthology.
            similarity: Relevance score calculated during search.

        Returns:
            Paper object.
        """
        def _get_str_attr(obj: Any, name: str, default: str = "") -> str:
            """Get a string attribute from an object, handling MarkupText and other types."""
            value = getattr(obj, name, default)
            if value is None:
                return default
            return str(value)

        return Paper(
            title=_get_str_attr(paper, 'title', '').strip(),
            authors=self._parse_authors(getattr(paper, 'authors', [])),
            year=int(getattr(paper, 'year', 0)) if getattr(paper, 'year') else None,
            abstract=_get_str_attr(paper, 'abstract', '').strip() if hasattr(paper, 'abstract') else "",
            source="acl_anthology",
            identifier=_get_str_attr(paper, 'id', ''),
            url=_get_str_attr(paper, 'web_url', ''),
            pdf_url=self._parse_pdf_url(paper),
            published=_get_str_attr(paper, 'ingest_date', ''),
            categories=[_get_str_attr(paper, 'venue', '')] if getattr(paper, 'venue', '') else [],
            similarity=similarity if similarity > 0 else None,
        )
    
    def _parse_authors(self, authors: Any) -> List[str]:
        if not authors:
            return []
        if isinstance(authors, list):
            return [f"{getattr(a, 'first', '')} {getattr(a, 'last', '')}".strip() for a in authors]

    def _parse_pdf_url(self, paper: Any) -> str:
        web_url = getattr(paper, 'web_url', '')
        if web_url and web_url.endswith('/'):
            return web_url[:-1] + '.pdf'
        elif web_url:
            return web_url + '.pdf'
        return ""

    def _download_file(self, url: str, identifier: str) -> Tuple[str, str]:
        """
        Download a file from a URL and save it to the download directory.

        Args:
            url: URL of the file to download.
            identifier: Identifier for naming the downloaded file.

        Returns:
            Tuple of (file path, filename).
        """
        import requests

        filename = f"{identifier.replace('/', '_')}.pdf"
        path = self.download_dir / filename

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            with open(path, "wb") as f:
                f.write(response.content)
            return str(path), filename
        except Exception as e:
            raise RuntimeError(f"Failed to download file from {url}: {str(e)}")
