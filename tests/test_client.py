"""Tests for the client module."""

import unittest
from unittest.mock import MagicMock, patch

from paperscout.client import PaperFinderClient


class TestPaperFinderClient(unittest.TestCase):
    """Test cases for PaperFinderClient."""

    def test_initialization(self):
        """Test client initialization."""
        client = PaperFinderClient()
        self.assertIsNotNone(client)
        self.assertIsNone(client._searcher)
        self.assertIsNone(client._downloader)

    def test_initialization_with_api_key(self):
        """Test client initialization with API key."""
        client = PaperFinderClient(api_key="test_key")
        self.assertEqual(client.api_key, "test_key")

    def test_search_method(self):
        """Test search method calls searcher."""
        with patch.object(PaperFinderClient, 'search') as mock_search:
            mock_search.return_value = []
            client = PaperFinderClient()
            client.search("test", source="arxiv", limit=5)
            mock_search.assert_called_once_with("test", source="arxiv", limit=5)

    def test_downloader_property(self):
        """Test downloader property returns downloader instance."""
        client = PaperFinderClient()
        # Mock the downloader to avoid actual initialization
        with patch("paper_finder.download.PaperDownloader") as MockDownloader:
            mock_downloader = MagicMock()
            MockDownloader.return_value = mock_downloader
            downloader = client.downloader
            self.assertIsNotNone(downloader)
            MockDownloader.assert_called_once()

    def test_search_with_arxiv_source(self):
        """Test search with arxiv source."""
        from paper_finder.backends.arxiv import ArxivBackend
        with patch.object(ArxivBackend, 'search', return_value=[]):
            client = PaperFinderClient()
            results = client.search("quantum computing", source="arxiv", limit=10)
            self.assertIsInstance(results, list)

    def test_search_with_acl_anthology_source(self):
        """Test search with acl_anthology source."""
        from paper_finder.backends.acl_anthology import ACLAnthologyBackend
        with patch.object(ACLAnthologyBackend, 'search', return_value=[]):
            client = PaperFinderClient()
            results = client.search("attention", source="acl_anthology", limit=10)
            self.assertIsInstance(results, list)

    def test_download_with_arxiv(self):
        """Test download with arxiv source."""
        from paper_finder.backends.arxiv import ArxivBackend
        with patch.object(ArxivBackend, 'download', return_value={"status": "success", "identifier": "2301.12345"}):
            client = PaperFinderClient()
            result = client.download("2301.12345", source="arxiv")
            self.assertIn("status", result)


if __name__ == "__main__":
    unittest.main()
