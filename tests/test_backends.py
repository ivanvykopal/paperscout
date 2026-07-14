"""Tests for the backend architecture."""

import unittest
from unittest.mock import MagicMock, patch

import pytest

from paperscout.backends.base import BaseBackend


class TestBaseBackend(unittest.TestCase):
    """Test cases for BaseBackend."""

    def test_base_backend_is_abstract(self):
        """Test that BaseBackend cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            BaseBackend()


class TestArxivBackend(unittest.TestCase):
    """Test cases for ArxivBackend."""

    def test_arxiv_backend_inherits_base(self):
        """Test that ArxivBackend inherits from BaseBackend."""
        with patch("paperscout.backends.arxiv.ARXIVY_AVAILABLE", True):
            with patch("paperscout.backends.arxiv.ArxivBackend.__init__", return_value=None):
                from paperscout.backends.arxiv import ArxivBackend
                backend = ArxivBackend()
                backend.client = None  # Mock client
                self.assertIsInstance(backend, BaseBackend)

    def test_arxiv_backend_search_method_exists(self):
        """Test that ArxivBackend has a search method."""
        with patch("paperscout.backends.arxiv.ARXIVY_AVAILABLE", True):
            with patch("paperscout.backends.arxiv.ArxivBackend.__init__", return_value=None):
                from paperscout.backends.arxiv import ArxivBackend
                backend = ArxivBackend()
                self.assertTrue(hasattr(backend, 'search'))
                self.assertTrue(callable(getattr(backend, 'search')))


class TestDblpBackend(unittest.TestCase):
    """Test cases for DblpBackend."""

    def test_dblp_backend_inherits_base(self):
        """Test that DblpBackend inherits from BaseBackend."""
        with patch("paperscout.backends.dblp.DBLPCLI_AVAILABLE", True):
            with patch("paperscout.backends.dblp.DblpBackend.__init__", return_value=None):
                from paperscout.backends.dblp import DblpBackend
                backend = DblpBackend()
                backend.client = None  # Mock client
                self.assertIsInstance(backend, BaseBackend)

    def test_dblp_backend_search_method_exists(self):
        """Test that DblpBackend has a search method."""
        with patch("paperscout.backends.dblp.DBLPCLI_AVAILABLE", True):
            with patch("paperscout.backends.dblp.DblpBackend.__init__", return_value=None):
                from paperscout.backends.dblp import DblpBackend
                backend = DblpBackend()
                self.assertTrue(hasattr(backend, 'search'))
                self.assertTrue(callable(getattr(backend, 'search')))


class TestSemanticScholarBackend(unittest.TestCase):
    """Test cases for SemanticScholarBackend."""

    def test_s2_backend_inherits_base(self):
        """Test that SemanticScholarBackend inherits from BaseBackend."""
        with patch("paperscout.backends.s2cli.S2CLI_AVAILABLE", True):
            with patch("paperscout.backends.s2cli.SemanticScholarBackend.__init__", return_value=None):
                from paperscout.backends.s2cli import SemanticScholarBackend
                backend = SemanticScholarBackend()
                backend.client = None  # Mock client
                self.assertIsInstance(backend, BaseBackend)

    def test_s2_backend_search_method_exists(self):
        """Test that SemanticScholarBackend has a search method."""
        with patch("paperscout.backends.s2cli.S2CLI_AVAILABLE", True):
            with patch("paperscout.backends.s2cli.SemanticScholarBackend.__init__", return_value=None):
                from paperscout.backends.s2cli import SemanticScholarBackend
                backend = SemanticScholarBackend()
                self.assertTrue(hasattr(backend, 'search'))
                self.assertTrue(callable(getattr(backend, 'search')))


class TestACLAnthologyBackend(unittest.TestCase):
    """Test cases for ACLAnthologyBackend."""

    def test_acl_backend_inherits_base(self):
        """Test that ACLAnthologyBackend inherits from BaseBackend."""
        with patch("paperscout.backends.acl_anthology.ACL_ANTHOLOGY_AVAILABLE", True):
            with patch("paperscout.backends.acl_anthology.ACLAnthologyBackend.__init__", return_value=None):
                from paperscout.backends.acl_anthology import ACLAnthologyBackend
                backend = ACLAnthologyBackend()
                backend.client = None  # Mock client
                self.assertIsInstance(backend, BaseBackend)

    def test_acl_backend_search_method_exists(self):
        """Test that ACLAnthologyBackend has a search method."""
        with patch("paperscout.backends.acl_anthology.ACL_ANTHOLOGY_AVAILABLE", True):
            with patch("paperscout.backends.acl_anthology.ACLAnthologyBackend.__init__", return_value=None):
                from paperscout.backends.acl_anthology import ACLAnthologyBackend
                backend = ACLAnthologyBackend()
                self.assertTrue(hasattr(backend, 'search'))
                self.assertTrue(callable(getattr(backend, 'search')))


def test_http_client_base_url_defaults_to_hf_space():
    from paperscout.backends.acl_anthology import _ACLAnthologyHTTPClient
    client = _ACLAnthologyHTTPClient()
    assert client.base_url == "https://ivykopal-acl-api.hf.space"


def test_http_client_base_url_respects_env_var(monkeypatch):
    from paperscout.backends.acl_anthology import _ACLAnthologyHTTPClient
    monkeypatch.setenv("PAPERSCOUT_ACL_API_URL", "http://localhost:8000")
    client = _ACLAnthologyHTTPClient()
    assert client.base_url == "http://localhost:8000"


def test_http_client_base_url_constructor_wins_over_env_var(monkeypatch):
    from paperscout.backends.acl_anthology import _ACLAnthologyHTTPClient
    monkeypatch.setenv("PAPERSCOUT_ACL_API_URL", "http://localhost:8000")
    client = _ACLAnthologyHTTPClient(base_url="http://example.com")
    assert client.base_url == "http://example.com"


def test_http_client_strips_trailing_slash():
    from paperscout.backends.acl_anthology import _ACLAnthologyHTTPClient
    client = _ACLAnthologyHTTPClient(base_url="http://localhost:8000/")
    assert client.base_url == "http://localhost:8000"


def test_request_with_retry_succeeds_immediately():
    from paperscout.backends.acl_anthology import _ACLAnthologyHTTPClient
    client = _ACLAnthologyHTTPClient()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "ok"}
    with patch("requests.request", return_value=mock_response) as mock_request:
        response = client._request_with_retry("GET", "/health")
        assert response.status_code == 200
        assert mock_request.call_count == 1


def test_request_with_retry_retries_on_503_then_succeeds():
    from paperscout.backends.acl_anthology import _ACLAnthologyHTTPClient
    client = _ACLAnthologyHTTPClient(max_retry_wait=2.0)
    bad = MagicMock()
    bad.status_code = 503
    bad.raise_for_status.side_effect = Exception("503")
    good = MagicMock()
    good.status_code = 200
    good.json.return_value = {"status": "ok"}
    with patch("requests.request", side_effect=[bad, good]) as mock_request:
        response = client._request_with_retry("GET", "/health")
        assert response.status_code == 200
        assert mock_request.call_count == 2


def test_request_with_retry_gives_up_after_max_wait():
    from paperscout.backends.acl_anthology import _ACLAnthologyHTTPClient
    client = _ACLAnthologyHTTPClient(max_retry_wait=0.1)
    bad = MagicMock()
    bad.status_code = 503
    bad.raise_for_status.side_effect = Exception("503")
    with patch("requests.request", return_value=bad) as mock_request:
        with pytest.raises(Exception):
            client._request_with_retry("GET", "/health")
        assert mock_request.call_count >= 1


def test_paper_from_api_maps_all_fields():
    from paperscout.backends.acl_anthology import _ACLAnthologyHTTPClient
    from paperscout.types import Paper
    client = _ACLAnthologyHTTPClient()
    data = {
        "id": "N18-3011",
        "title": "Attention Is All You Need",
        "abstract": "We propose a new simple network architecture.",
        "authors": "Ashish Vaswani, Noam Shazeer",
        "venue": "NLP",
        "year": 2017,
        "url": "https://aclanthology.org/N18-3011/",
        "bibtex": "@inproceedings{...}",
        "pdf_url": "https://aclanthology.org/N18-3011.pdf",
    }
    paper = client._paper_from_api(data, similarity=0.95)
    assert isinstance(paper, Paper)
    assert paper.identifier == "N18-3011"
    assert paper.title == "Attention Is All You Need"
    assert paper.authors == ["Ashish Vaswani", "Noam Shazeer"]
    assert paper.year == 2017
    assert paper.abstract == "We propose a new simple network architecture."
    assert paper.categories == ["NLP"]
    assert paper.url == "https://aclanthology.org/N18-3011/"
    assert paper.pdf_url == "https://aclanthology.org/N18-3011.pdf"
    assert paper.similarity == 0.95
    assert paper.source == "acl_anthology"


def test_paper_from_api_handles_null_year_and_empty_fields():
    from paperscout.backends.acl_anthology import _ACLAnthologyHTTPClient
    client = _ACLAnthologyHTTPClient()
    data = {
        "id": "1993.tc-1.6",
        "title": "Terminology and the computer",
        "abstract": "",
        "authors": "",
        "venue": "",
        "year": None,
        "url": "https://aclanthology.org/1993.tc-1.6/",
        "bibtex": "",
        "pdf_url": "",
    }
    paper = client._paper_from_api(data)
    assert paper.year is None
    assert paper.authors == []
    assert paper.categories == []
    assert paper.pdf_url == ""


if __name__ == "__main__":
    unittest.main()
