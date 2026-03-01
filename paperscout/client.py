"""
Main client for the Paper Finder package.
"""

from typing import Dict, List, Optional

from paperscout.types import Paper


class PaperFinderClient:
    """
    Main client for interacting with the Paper Finder API.

    Provides methods for searching, downloading, and managing academic papers.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Paper Finder client.

        Args:
            api_key: Optional API key for services that require authentication.
        """
        self.api_key = api_key
        self._searcher = None
        self._downloader = None

    @property
    def searcher(self):
        """Get the paper searcher instance."""
        if self._searcher is None:
            from paperscout.search import PaperSearcher

            self._searcher = PaperSearcher()
        return self._searcher

    @property
    def downloader(self):
        """Get the paper downloader instance."""
        if self._downloader is None:
            from paperscout.download import PaperDownloader

            self._downloader = PaperDownloader()
        return self._downloader

    def search(
        self,
        query: str,
        source: str = "arxiv",
        limit: int = 10,
        **kwargs,
    ) -> List[Paper]:
        """
        Search for academic papers.

        Args:
            query: Search query string.
            source: Source to search (arxiv, pubmed, google_scholar).
            limit: Maximum number of results to return.
            **kwargs: Additional source-specific parameters.

        Returns:
            List of Paper objects.
        """
        return self.searcher.search(query, source, limit, **kwargs)

    def download(self, identifier: str, source: str = "arxiv", **kwargs) -> Dict:
        """
        Download a paper by identifier (DOI, arXiv ID, etc.).

        Args:
            identifier: Unique paper identifier.
            source: Source to download from.
            **kwargs: Download options.

        Returns:
            Path to the downloaded paper or paper metadata.
        """
        return self.searcher.download(identifier, source, **kwargs)
