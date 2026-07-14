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

    @property
    def last_search_total(self) -> int:
        """The total number of results found by the last search (across all backends)."""
        if self._searcher is None:
            return 0
        return self._searcher.last_search_total

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

    def download(
        self,
        identifier: str,
        source: Optional[str] = None,
        output_dir: Optional[str] = None,
        **kwargs,
    ) -> Dict:
        """
        Download a paper by identifier (DOI, arXiv ID, etc.).

        The identifier type is auto-detected (arXiv, DOI, ACL, DBLP, etc.)
        so you don't need to specify the source manually.

        Args:
            identifier: Unique paper identifier (DOI, arXiv ID, ACL ID, DBLP key, etc.).
            source: Source to download from. Auto-detected if not provided.
            output_dir: Directory to save the PDF. Defaults to ./downloads.
            **kwargs: Additional backend-specific options.

        Returns:
            Dictionary with download information (status, path, filename, title, etc.).
        """
        return self.downloader.download(
            identifier, source=source, output_dir=output_dir, **kwargs
        )

    def verify_bibtex(
        self,
        path: str,
        sources: list[str] | None = None,
        enrich: bool = False,
        threshold: float = 0.5,
        parallel: bool = False,
    ) -> list:
        """
        Verify BibTeX entries in a file.

        Args:
            path: Path to .bib file.
            sources: Specific backends to use.
            enrich: Whether to enrich entries.
            threshold: Confidence threshold.
            parallel: Whether to run in parallel.

        Returns:
            List of VerificationResult objects.
        """
        from paperscout.bibtex import BibtexVerifier

        verifier = BibtexVerifier(threshold=threshold)
        return verifier.verify_file(path, sources=sources, enrich=enrich, parallel=parallel)

    def verify_markdown_references(
        self,
        path: str,
        sources: list[str] | None = None,
        threshold: float = 0.5,
    ) -> list:
        """
        Verify references extracted from a markdown file.

        Args:
            path: Path to .md file with References section.
            sources: Specific backends to use.
            threshold: Confidence threshold.

        Returns:
            List of ReferenceVerificationResult objects.
        """
        from paperscout.markdown_refs import MarkdownRefParser

        parser = MarkdownRefParser()
        # Note: threshold is currently used internally by the parser via BibtexVerifier
        return parser.verify_file(path, sources=sources)
