"""
Semantic Scholar backend using the s2cli library.
"""

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from paperscout.backends.base import BaseBackend
from s2cli.api.client import SemanticScholarAPI

try:
    import s2cli
    S2CLI_AVAILABLE = True
except ImportError:
    S2CLI_AVAILABLE = False


class SemanticScholarBackend(BaseBackend):
    """
    Backend for searching and downloading papers from Semantic Scholar.

    Uses the s2cli library for Semantic Scholar API interactions.
    """

    name: str = "semantic_scholar"
    supported_sources: List[str] = ["semantic_scholar", "Semantic Scholar"]

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Semantic Scholar backend.

        Args:
            api_key: Optional API key (not typically required for arXiv).
        """
        super().__init__(api_key)
        self.client = SemanticScholarAPI(api_key=api_key)
        self.download_dir = Path(tempfile.gettempdir()) / "paperscout" / "s2cli"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        if not S2CLI_AVAILABLE:
            raise ImportError(
                "s2cli is not installed. Install it with: pip install s2cli"
            )

    def search(
            self,
            query: str,
            limit: int = 10
        ) -> List[Dict]:
        """
        Search for papers on Semantic Scholar.

        Args:
            query: Search query string.
            limit: Maximum number of results to return.
            category: Optional category to filter results (e.g., 'cs.LG').
            sort_by: Optional field to sort by ('relevance', 'lastUpdatedDate', 'submittedDate').
            sort_order: Optional sort order ('ascending' or 'descending').

        Returns:
            List of paper search results as dictionaries.
        """
        results = self.client.search_papers(
            query=query,
            limit=limit
        )

        return [self._format_result(result) for result in results]

    def download(self, identifier: str) -> Dict:
        """
        Download a paper from Semantic Scholar.

        Args:
            identifier: Semantic Scholar ID (e.g., '1234567890abcdef1234567890abcdef').

        Returns:
            Dictionary with download information including path.
        """
        paper = self.client.get_paper(identifier)
        if not paper:
            return {"status": "error", "message": f"Paper with ID {identifier} not found."}

        # get pdf_url from result
        pdf_url = paper.get("pdf_url", "")
        if not pdf_url:
            return {"status": "error", "message": f"No PDF URL found for paper with ID {identifier}."}
        
        path, filename = self._download_file(pdf_url, identifier)

        return {
            "status": "success",
            "identifier": identifier,
            "path": path,
            "filename": filename,
            "title": paper.get("title", ""),
            "authors": paper.get("authors", []),
        }

    def _format_result(self, result: Dict) -> Dict:
        """
        Format Semantic Scholar result dictionary to standard format.

        Args:
            result: Raw result from Semantic Scholar query.

        Returns:
            Formatted result dictionary.
        """
        return result
        # return {
        #     "title": result.title.strip(),
        #     "authors": [author.name.strip() for author in result.authors],
        #     "year": int(result.published.split("-")[0]) if result.published else None,
        #     "abstract": result.summary.strip() if hasattr(result, 'summary') else "",
        #     "source": "semantic_scholar",
        #     "identifier": result.s2_id,
        #     "url": result.abstract_url if hasattr(result, 'abstract_url') else "",
        #     "pdf_url": result.pdf_url if hasattr(result, 'pdf_url') else "",
        #     "published": result.published,
        #     "categories": result.categories if hasattr(result, 'categories') else [],
        # }
    
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
