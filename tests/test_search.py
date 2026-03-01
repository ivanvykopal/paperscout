"""Tests for the search module."""

import unittest
from unittest.mock import patch

from paperscout.search import PaperSearcher
from paperscout.similarity import _title_similarity, _normalize_title


class TestTitleSimilarity(unittest.TestCase):
    """Test cases for title similarity functions."""

    def test_normalize_title(self):
        """Test title normalization."""
        self.assertEqual(_normalize_title("Hello World"), "hello world")
        self.assertEqual(_normalize_title("  Hello   World  "), "hello world")
        self.assertEqual(_normalize_title("Hello, World!"), "hello world")
        self.assertEqual(_normalize_title(""), "")
        self.assertEqual(_normalize_title(None), "")

    def test_title_similarity_exact_match(self):
        """Test exact title match returns 1.0."""
        self.assertEqual(_title_similarity("Attention Is All You Need", "Attention Is All You Need"), 1.0)

    def test_title_similarity_no_match(self):
        """Test completely different titles return 0."""
        self.assertEqual(_title_similarity("Machine Learning", "Cooking Recipes"), 0.0)

    def test_title_similarity_partial_match(self):
        """Test partial title match."""
        score = _title_similarity("Attention Is All You Need", "Attention Is All")
        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)


class TestPaperSearcher(unittest.TestCase):
    """Test cases for PaperSearcher."""

    def setUp(self):
        """Set up test fixtures."""
        self.searcher = PaperSearcher()

    def test_invalid_source_raises_error(self):
        """Test searching with invalid source raises error."""
        with self.assertRaises(ValueError):
            self.searcher.search("test", source="invalid_source")

    def test_search_arxiv_backend_registered(self):
        """Test arxiv backend can be used."""
        from paper_finder.backends.arxiv import ArxivBackend
        with patch.object(ArxivBackend, 'search', return_value=[]):
            results = self.searcher.search("quantum", source="arxiv", limit=3)
            self.assertIsInstance(results, list)

    def test_search_acl_anthology_backend_registered(self):
        """Test acl_anthology backend can be used."""
        from paper_finder.backends.acl_anthology import ACLAnthologyBackend
        with patch.object(ACLAnthologyBackend, 'search', return_value=[]):
            results = self.searcher.search("attention", source="acl_anthology", limit=3)
            self.assertIsInstance(results, list)

    def test_search_dblp_backend_registered(self):
        """Test dblp backend can be used."""
        from paper_finder.backends.dblp import DblpBackend
        with patch.object(DblpBackend, 'search', return_value=[]):
            results = self.searcher.search("transformer", source="dblp", limit=3)
            self.assertIsInstance(results, list)

    def test_search_s2_backend_registered(self):
        """Test semantic_scholar backend can be used."""
        from paper_finder.backends.s2cli import SemanticScholarBackend
        with patch.object(SemanticScholarBackend, 'search', return_value=[]):
            results = self.searcher.search("transformer", source="semantic_scholar", limit=3)
            self.assertIsInstance(results, list)

    def test_download_method(self):
        """Test download method exists and calls backend."""
        from paper_finder.backends.arxiv import ArxivBackend
        with patch.object(ArxivBackend, 'download', return_value={"status": "success", "identifier": "test"}):
            result = self.searcher.download("2301.12345", source="arxiv")
            self.assertIn("status", result)
            self.assertIn("identifier", result)

    def test_search_all_backends(self):
        """Test searching all backends returns list."""
        # Mock all backends to return empty results
        backends = [
            'paper_finder.backends.arxiv.ArxivBackend',
            'paper_finder.backends.dblp.DblpBackend',
            'paper_finder.backends.s2cli.SemanticScholarBackend',
            'paper_finder.backends.acl_anthology.ACLAnthologyBackend',
        ]
        with patch(backends[0], autospec=True) as mock_arxiv, \
             patch(backends[1], autospec=True) as mock_dblp, \
             patch(backends[2], autospec=True) as mock_s2, \
             patch(backends[3], autospec=True) as mock_acl:
            # Set search to return empty lists
            for mock_backend in [mock_arxiv, mock_dblp, mock_s2, mock_acl]:
                mock_backend.return_value.search.return_value = []
                mock_backend.return_value.download.return_value = {"status": "success", "identifier": "test"}
            results = self.searcher.search("test", source="all", limit=5)
            self.assertIsInstance(results, list)

    def test_search_all_no_results(self):
        """Test searching all backends when no backends available."""
        # Test should handle gracefully when backends aren't available
        results = self.searcher.search("test", source="all", limit=5)
        self.assertIsInstance(results, list)


if __name__ == "__main__":
    unittest.main()
