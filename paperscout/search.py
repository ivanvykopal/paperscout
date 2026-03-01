"""
Paper search functionality using backend implementations.
"""

from typing import Dict, List

from paperscout.backends.arxiv import ArxivBackend
from paperscout.backends.base import BaseBackend
from paperscout.backends.dblp import DblpBackend
from paperscout.backends.s2cli import SemanticScholarBackend
from paperscout.backends.acl_anthology import ACLAnthologyBackend
from paperscout.similarity import _title_similarity
from paperscout.types import Paper


# Mapping of common shortcuts to their full names for query expansion
SHORTCUTS = {
    "llms": "large language models",
    "llm": "large language model",
    "nlp": "natural language processing",
    "bert": "bidirectional encoder representations from transformers",
    "gpt": "generative pre-trained transformer",
    "rag": "retrieval-augmented generation",
    "finetuning": "fine-tuning",
    "pretraining": "pre-training",
    "sft": "supervised fine-tuning",
    "rlhf": "reinforcement learning with human feedback",
    "rl": "reinforcement learning",
    "fewshot": "few-shot learning",
    "zeroshot": "zero-shot learning",
}


def _expand_shortcuts(query: str) -> str:
    """Expand shortcuts in the query to their full names."""
    words = query.split()
    expanded_words = []

    for word in words:
        # Check if word (lowercase) is a shortcut
        word_lower = word.lower().rstrip(",.;:")
        if word_lower in SHORTCUTS:
            # Preserve the original casing if it's a match
            expansion = SHORTCUTS[word_lower]
            # Keep any punctuation that was attached to the word
            punctuation = word[len(word_lower):]
            expanded_words.append(expansion + punctuation)
        else:
            expanded_words.append(word)

    return " ".join(expanded_words)


class PaperSearcher:
    """
    Search for academic papers using pluggable backends.

    Supports searching across multiple sources for the best match.
    """

    BACKENDS = {
        "acl_anthology": ACLAnthologyBackend,
        "arxiv": ArxivBackend,
        "dblp": DblpBackend,
        "semantic_scholar": SemanticScholarBackend,
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
    ) -> List[Paper]:
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
            **kwargs: Backend-specific parameters.

        Returns:
            List of Paper objects, sorted by similarity.
        """
        expanded_query = _expand_shortcuts(query)

        if source == "all":
            return self._search_all_backends(query, expanded_query, limit, exact_match_first, **kwargs)
        else:
            backend = self._get_backend(source)
            # Search with both queries and combine results, only if the queries are different
            if expanded_query != query:
                original_results = backend.search(query, limit=limit, **kwargs)
                expanded_results = backend.search(expanded_query, limit=limit, **kwargs)
                combined_results = self._combine_results(original_results, expanded_results)
            else:
                combined_results = backend.search(query, limit=limit, **kwargs)
            
            for result in combined_results:
                new_similarity = _title_similarity(query, result.title)
                if result.similarity is None or result.similarity < new_similarity:
                    result.similarity = new_similarity
            return combined_results

    def _search_all_backends(
        self,
        query: str,
        expanded_query: str,
        limit: int,
        exact_match_first: bool,
        **kwargs,
    ) -> List[Paper]:
        """
        Search across all backends and return best matches.

        Args:
            query: Original search query string.
            expanded_query: Query with shortcuts expanded.
            limit: Maximum number of results to return.
            exact_match_first: Prefer exact title matches.
            **kwargs: Backend-specific parameters.

        Returns:
            List of Paper objects from all backends, sorted by similarity.
        """
        all_results: List[Paper] = []

        for source_name, backend_class in self.BACKENDS.items():
            try:
                backend = self._get_backend(source_name)
                original_results = backend.search(query, limit=limit, **kwargs)
                expanded_results = backend.search(expanded_query, limit=limit, **kwargs)
                combined = self._combine_results(original_results, expanded_results)

                for result in combined:
                    result.source = source_name
                    new_similarity = _title_similarity(query, result.title)
                    if result.similarity is None or result.similarity < new_similarity:
                        result.similarity = new_similarity
                    all_results.append(result)

            except Exception as e:
                continue

        if not all_results:
            return []

        def sort_key(paper: Paper):
            similarity = paper.similarity or 0
            source = paper.source
            if source == "acl_anthology":
                return (0, -similarity)
            else:
                return (1, -similarity)

        all_results.sort(key=sort_key)

        # If exact match first is enabled, move exact matches to top
        if exact_match_first:
            exact_matches = [r for r in all_results if (r.similarity or 0) == 1.0]
            similar_matches = [r for r in all_results if (r.similarity or 0) < 1.0]
            all_results = exact_matches + similar_matches

        # Apply limit
        return all_results[:limit]

    def _combine_results(self, results1: List[Paper], results2: List[Paper]) -> List[Paper]:
        """
        Combine two result lists, keeping the highest similarity for duplicate papers.

        Args:
            results1: First list of Paper objects.
            results2: Second list of Paper objects.

        Returns:
            Combined list of Paper objects with highest similarity per paper.
        """
        # Use paper identifier + title as the key for deduplication

        combined = {}

        for paper in results1:
            key = (paper.identifier, paper.title.lower())
            combined[key] = paper

        for paper in results2:
            key = (paper.identifier, paper.title.lower())
            if key in combined:
                # Keep the one with higher similarity (treat None as 0)
                sim2 = paper.similarity if paper.similarity is not None else 0
                sim1 = combined[key].similarity if combined[key].similarity is not None else 0
                if sim2 > sim1:
                    combined[key] = paper
            else:
                combined[key] = paper

        return list(combined.values())

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
