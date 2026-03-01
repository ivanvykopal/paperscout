"""
ArXiv backend using the arxivy library.
"""

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from paperscout.backends.base import BaseBackend
from arxivy.api.client import ArxivClient

try:
    import arxivy
    ARXIVY_AVAILABLE = True
except ImportError:
    ARXIVY_AVAILABLE = False


class ArxivBackend(BaseBackend):
    """
    Backend for searching and downloading papers from arXiv.

    Uses the arxivy library for arXiv API interactions.
    """

    name: str = "arxiv"
    supported_sources: List[str] = ["arxiv", "arXiv"]

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the arXiv backend.

        Args:
            api_key: Optional API key (not typically required for arXiv).
        """
        super().__init__(api_key)
        self.client = ArxivClient()
        self.download_dir = Path(tempfile.gettempdir()) / "paperscout" / "arxiv"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        if not ARXIVY_AVAILABLE:
            raise ImportError(
                "arxivy is not installed. Install it with: pip install arxivy"
            )

    def search(
            self,
            query: str,
            limit: int = 10,
            category: Optional[str] = None,
            sort_by: Optional[str] = None,
            sort_order: Optional[str] = None,
        ) -> List[Dict]:
        """
        Search for papers on arXiv.

        Args:
            query: Search query string.
            limit: Maximum number of results to return.
            category: Optional category to filter results (e.g., 'cs.LG').
            sort_by: Optional field to sort by ('relevance', 'lastUpdatedDate', 'submittedDate').
            sort_order: Optional sort order ('ascending' or 'descending').

        Returns:
            List of paper search results as dictionaries.
        """
        papers = self.client.search(
            query=query,
            limit=limit,
            category=category,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return [self._format_result(result) for result in papers.results]

    def download(self, identifier: str) -> Dict:
        """
        Download a paper from arXiv.

        Args:
            identifier: arXiv ID (e.g., '2301.12345' or 'arXiv:2301.12345').

        Returns:
            Dictionary with download information including path.
        """
        paper = self.client.get_paper(identifier)
        if not paper:
            return {"status": "error", "message": f"Paper with ID {identifier} not found."}

        # get pdf_url from result
        pdf_url = paper.pdf_url
        if not pdf_url:
            return {"status": "error", "message": f"No PDF URL found for paper with ID {identifier}."}
        
        path, filename = self._download_file(pdf_url, identifier)

        return {
            "status": "success",
            "identifier": identifier,
            "path": path,
            "filename": filename,
            "title": paper.title,
            "authors": paper.authors,
        }

    def _format_result(self, result: Any) -> Dict:
        """
        Format arxivy result dictionary to standard format.

        Args:
            result: Raw result from arxivy query.

        Returns:
            Formatted result dictionary.
        """
        return {
            "title": result.title.strip(),
            "authors": [author.name.strip() for author in result.authors],
            "year": int(result.published.split("-")[0]) if result.published else None,
            "abstract": result.summary.strip() if hasattr(result, 'summary') else "",
            "source": "arxiv",
            "identifier": result.arxiv_id,
            "url": result.abstract_url if hasattr(result, 'abstract_url') else "",
            "pdf_url": result.pdf_url if hasattr(result, 'pdf_url') else "",
            "published": result.published,
            "categories": result.categories if hasattr(result, 'categories') else [],
        }
    
    def _download_file(self, url: str, identifier: str) -> Tuple[str, str]:
        """
        Download a file from a URL and save it to the download directory.

        Args:
            url: URL of the file to download.
            identifier: Identifier for naming the downloaded file.
        Returns:
            Tuple of (file path, filename).
        """
        filename = f"{identifier.replace('/', '_')}.pdf"
        path = self.download_dir / filename
        try:
            # do now use arxivy to download
            import requests
            response = requests.get(url)
            response.raise_for_status()
            with open(path, "wb") as f:
                f.write(response.content)
            return str(path), filename
        except Exception as e:
            raise RuntimeError(f"Failed to download file from {url}: {str(e)}")
