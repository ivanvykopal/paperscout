"""
DBLP backend using the dblpcli library.
"""

import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from paperscout.backends.base import BaseBackend
from dblpcli.api.client import DBLPClient
from paperscout.types import Paper

try:
    import dblpcli
    DBLPCLI_AVAILABLE = True
except ImportError:
    DBLPCLI_AVAILABLE = False


class DblpBackend(BaseBackend):
    """
    Backend for searching and downloading papers from DBLP.

    Uses the dblpcli library for DBLP API interactions.
    """

    name: str = "dblp"
    supported_sources: List[str] = ["dblp", "DBLP"]

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the DBLP backend.

        Args:
            api_key: Optional API key (not typically required for arXiv).
        """
        super().__init__(api_key)
        self.client = DBLPClient()
        self.download_dir = Path(tempfile.gettempdir()) / "paperscout" / "dblp"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        if not DBLPCLI_AVAILABLE:
            raise ImportError(
                "dblpcli is not installed. Install it with: pip install dblpcli"
            )

    def search(
            self,
            query: str,
            limit: int = 10
        ) -> List[Paper]:
        """
        Search for papers on DBLP.

        Args:
            query: Search query string.
            limit: Maximum number of results to return.

        Returns:
            List of Paper objects.
        """
        try:
            results = self.client.search_publications(
                query=query,
                limit=limit
            )
        except ET.ParseError as e:
            raise RuntimeError(
                "DBLP returned a non-XML page (bot challenge or rate limit); results unavailable"
            ) from e

        # Capture the total result count from the API metadata
        self._last_total = results.get("meta", {}).get("total", 0)

        return [self._format_result(result) for result in results.get("results", [])]

    def download(self, identifier: str, output_dir: Optional[str] = None) -> Dict:
        """
        Download a paper from DBLP.

        Args:
            identifier: DBLP key (e.g., 'journals/corr/abs-2301-12345').
            output_dir: Directory to save the PDF (defaults to temp dir).

        Returns:
            Dictionary with download information including path.
        """
        save_dir = Path(output_dir) if output_dir else self.download_dir
        save_dir.mkdir(parents=True, exist_ok=True)

        paper = self.client.get_publication(identifier)
        if not paper:
            return {"status": "error", "message": f"Paper with ID {identifier} not found."}

        # get pdf_url from result
        pdf_url = paper.get("pdf_url", "")
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
        Format DBLP result to standard format.

        Args:
            result: Raw result from DBLP query.

        Returns:
            Paper object.
        """
        return Paper(
            title=result.get("title", "").strip(),
            authors=[author.strip() for author in result.get("authors", [])],
            year=int(result.get("year", 0)) if result.get("year") else None,
            abstract=result.get("abstract", "").strip(),
            source="dblp",
            identifier=result.get("key", ""),
            url=result.get("url", ""),
            pdf_url=result.get("pdf_url", ""),
            published=result.get("published", ""),
            categories=result.get("categories", []),
            similarity=None,
            venue=result.get("venue") or None,
            doi=result.get("doi") or None,
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
