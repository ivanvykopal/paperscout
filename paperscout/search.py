"""
Paper search functionality using backend implementations.
"""

from typing import Dict, List, Optional, Tuple

from paperscout.backends.arxiv import ArxivBackend
from paperscout.backends.base import BaseBackend
from paperscout.backends.dblp import DblpBackend
from paperscout.backends.s2cli import SemanticScholarBackend
from paperscout.backends.acl_anthology import ACLAnthologyBackend
from paperscout.similarity import _title_similarity


class PaperSearcher:
    """
    Search for academic papers using pluggable backends.

    Supports searching across multiple sources for the best match.
    """

    BACKENDS = {
        "arxiv": ArxivBackend,
        "dblp": DblpBackend,
        "semantic_scholar": SemanticScholarBackend,
        "acl_anthology": ACLAnthologyBackend,
    }

    def __init__(self):
        """Initialize the paper searcher with available backends."""
        self._backends: Dict[str, BaseBackend] = {}

    def search(
        self,
        query: str,
        source: str = "all",
        limit: int = 10,
        exact_match_first: bool = True,
        **kwargs,
    ) -> List[Dict]:
        """
        Search for papers using the appropriate backend(s).

        Args:
            query: Search query string (typically a paper title).
            source: Source to search. Use "all" to search all backends
                   and return the best matches. Individual sources:
                   "arxiv", "dblp", "semantic_scholar", "acl_anthology".
            limit: Maximum number of results to return.
            exact_match_first: If True, return exact title matches first,
                              then fall back to similar titles.
            **kwargs: Additional source-specific parameters.

        Returns:
            List of paper search results as dictionaries, sorted by similarity.
        """
        if source == "all":
            return self._search_all_backends(query, limit, exact_match_first, **kwargs)
        else:
            backend = self._get_backend(source)
            results = backend.search(query, limit, **kwargs)
            # Add similarity scores for cross-backend consistency
            for result in results:
                result["_similarity"] = _title_similarity(query, result.get("title", ""))
            return results

    def _search_all_backends(
        self,
        query: str,
        limit: int,
        exact_match_first: bool,
        **kwargs,
    ) -> List[Dict]:
        """
        Search across all backends and return best matches.

        Args:
            query: Search query string.
            limit: Maximum number of results to return.
            exact_match_first: Prefer exact title matches.
            **kwargs: Backend-specific parameters.

        Returns:
            List of results from all backends, sorted by similarity.
        """
        all_results: List[Dict] = []

        for source_name, backend_class in self.BACKENDS.items():
            try:
                backend = self._get_backend(source_name)
                results = backend.search(query, limit=limit, **kwargs)

                for result in results:
                    # Calculate similarity to the query
                    similarity = _title_similarity(query, result.get("title", ""))
                    result["_source"] = source_name
                    result["_similarity"] = similarity
                    all_results.append(result)

            except Exception as e:
                # Continue with other backends even if one fails
                continue

        if not all_results:
            return []

        # Sort by: ACL Anthology first, then by similarity (highest first)
        # ACL Anthology papers get a priority boost
        def sort_key(x):
            similarity = x.get("_similarity", 0)
            source = x.get("_source", "")
            # ACL Anthology papers come first, then sort by similarity
            if source == "acl_anthology":
                return (0, -similarity)  # 0 = highest priority
            else:
                return (1, -similarity)  # 1 = lower priority

        all_results.sort(key=sort_key)

        # If exact match first is enabled, move exact matches to top
        if exact_match_first:
            exact_matches = [
                r for r in all_results if r.get("_similarity", 0) == 1.0
            ]
            similar_matches = [
                r for r in all_results if r.get("_similarity", 0) < 1.0
            ]
            all_results = exact_matches + similar_matches

        # Remove internal fields and apply limit
        results = []
        for r in all_results[:limit]:
            r.pop("_source", None)
            r.pop("_similarity", None)
            results.append(r)

        return results

    def download(self, identifier: str, source: str = "arxiv", **kwargs) -> Dict:
        """
        Download a paper using the appropriate backend.

        Args:
            identifier: Unique paper identifier (DOI, arXiv ID, etc.).
            source: Source to download from (arxiv, dblp, semantic_scholar, acl_anthology).
            **kwargs: Backend-specific download options.

        Returns:
            Dictionary with download information.
        """
        backend = self._get_backend(source)
        return backend.download(identifier, **kwargs)

    def _get_backend(self, source: str) -> BaseBackend:
        """
        Get or create a backend instance for the given source.

        Args:
            source: Source name (e.g., 'arxiv', 'dblp', 'semantic_scholar', 'acl_anthology').

        Returns:
            Backend instance.

        Raises:
            ValueError: If source is not supported or backend not available.
        """
        source_lower = source.lower()

        if source_lower not in self.BACKENDS:
            raise ValueError(
                f"Source '{source}' is not supported. "
                f"Supported sources: {list(self.BACKENDS.keys())}"
            )

        if source_lower not in self._backends:
            backend_class = self.BACKENDS[source_lower]
            self._backends[source_lower] = backend_class()

        return self._backends[source_lower]
