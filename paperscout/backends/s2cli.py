"""
Semantic Scholar backend using the s2cli library.
"""

import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from paperscout.backends.base import BaseBackend
from s2cli.api.client import SemanticScholarAPI
from paperscout.types import Paper

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

    def __init__(
        self,
        api_key: Optional[str] = None,
        max_retries: int = 5,
        max_retry_wait: int = 120,
        retry_enabled: bool = True,
    ):
        """
        Initialize the Semantic Scholar backend.

        Args:
            api_key: Semantic Scholar API key for higher rate limits
                     (100 req/s with key vs 1 req/s without).
                     Can also be set via the S2_API_KEY environment variable.
            max_retries: Maximum number of retry attempts on rate limits (default 5).
            max_retry_wait: Maximum seconds to wait for any single retry (default 120).
            retry_enabled: Whether to automatically retry on rate limits.
        """
        super().__init__(api_key)
        self.client = SemanticScholarAPI(
            api_key=api_key,
            max_retries=max_retries,
            max_retry_wait=max_retry_wait,
            retry_enabled=retry_enabled,
        )
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
        ) -> List[Paper]:
        """
        Search for papers on Semantic Scholar.

        Args:
            query: Search query string.
            limit: Maximum number of results to return.
            category: Optional category to filter results (e.g., 'cs.LG').
            sort_by: Optional field to sort by ('relevance', 'lastUpdatedDate', 'submittedDate').
            sort_order: Optional sort order ('ascending' or 'descending').

        Returns:
            List of Paper objects.
        """
        results = self.client.search_papers(
            query=query,
            limit=limit
        )

        # Capture the total result count from the API metadata
        self._last_total = results.get("total", 0)

        return [self._format_result(result) for result in results.get("data", [])]

    def download(self, identifier: str, output_dir: Optional[str] = None) -> Dict:
        """
        Download a paper from Semantic Scholar.

        Args:
            identifier: Semantic Scholar ID or DOI.
            output_dir: Directory to save the PDF (defaults to temp dir).

        Returns:
            Dictionary with download information including path.
        """
        save_dir = Path(output_dir) if output_dir else self.download_dir
        save_dir.mkdir(parents=True, exist_ok=True)

        paper = self.client.get_paper(identifier)
        if not paper:
            return {"status": "error", "message": f"Paper with ID {identifier} not found."}

        # get pdf_url from result
        pdf_url = paper.get("pdf_url", "")
        if not pdf_url:
            # Try external IDs for a PDF URL
            external_ids = paper.get("externalIds", {}) or {}
            doi = external_ids.get("DOI", "")
            arxiv_id = external_ids.get("ArXiv", "")
            if arxiv_id:
                # Try to get PDF from arXiv
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            elif doi:
                pdf_url = f"https://doi.org/{doi}"

        if not pdf_url:
            return {"status": "error", "message": f"No PDF URL found for paper with ID {identifier}."}

        path, filename = self._download_file(pdf_url, identifier, save_dir)

        return {
            "status": "success",
            "identifier": identifier,
            "path": path,
            "filename": filename,
            "title": paper.get("title", ""),
            "authors": paper.get("authors", []),
        }

    def _format_result(self, result: Dict) -> Paper:
        """
        Format Semantic Scholar result dictionary to standard format.

        Args:
            result: Raw result from Semantic Scholar query.

        Returns:
            Paper object.
        """
        # S2 returns authors as [{"authorId": "...", "name": "..."}]
        raw_authors = result.get("authors", [])
        authors = (
            [a.get("name", "").strip() for a in raw_authors if isinstance(a, dict)]
            if raw_authors and isinstance(raw_authors[0], dict)
            else raw_authors
        )

        return Paper(
            title=result.get("title", "").strip(),
            authors=authors,
            year=int(result.get("year", 0)) if result.get("year") else None,
            abstract=result.get("abstract", "").strip(),
            source="semantic_scholar",
            identifier=result.get("s2_id", result.get("paperId", "")),
            url=result.get("url", ""),
            pdf_url=result.get("pdf_url", ""),
            published=result.get("published", ""),
            categories=result.get("venue", result.get("categories", [])),
            similarity=None,
        )
    
    def _download_file(self, url: str, identifier: str, save_dir: Optional[Path] = None) -> Tuple[str, str]:
        """
        Download a file from a URL and save it to the download directory.

        Args:
            url: URL of the file to download.
            identifier: Identifier for naming the downloaded file.
            save_dir: Directory to save the file (defaults to self.download_dir).
        Returns:
            Tuple of (file path, filename).
        """
        target_dir = save_dir if save_dir else self.download_dir
        filename = f"{identifier.replace('/', '_')}.pdf"
        path = target_dir / filename
        try:
            import requests
            response = requests.get(url)
            response.raise_for_status()
            with open(path, "wb") as f:
                f.write(response.content)
            return str(path), filename
        except Exception as e:
            raise RuntimeError(f"Failed to download file from {url}: {str(e)}")
