"""Tests for the backend architecture."""

import unittest
from pathlib import Path
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
            from paperscout.backends.acl_anthology import ACLAnthologyBackend
            with patch.object(ACLAnthologyBackend, "__init__", return_value=None):
                backend = ACLAnthologyBackend()
                backend._http_client = None
                backend._local_backend = None
                self.assertIsInstance(backend, BaseBackend)

    def test_acl_backend_search_method_exists(self):
        """Test that ACLAnthologyBackend has a search method."""
        with patch("paperscout.backends.acl_anthology.ACL_ANTHOLOGY_AVAILABLE", True):
            from paperscout.backends.acl_anthology import ACLAnthologyBackend
            with patch.object(ACLAnthologyBackend, "__init__", return_value=None):
                backend = ACLAnthologyBackend()
                self.assertTrue(hasattr(backend, "search"))
                self.assertTrue(callable(getattr(backend, "search")))


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


def test_search_similarity_calls_api_and_maps_results():
    from paperscout.backends.acl_anthology import _ACLAnthologyHTTPClient
    client = _ACLAnthologyHTTPClient()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "id": "N18-3011",
            "title": "Attention Is All You Need",
            "abstract": "",
            "authors": "",
            "venue": "",
            "year": 2017,
            "url": "https://aclanthology.org/N18-3011/",
            "bibtex": "",
            "pdf_url": "",
            "score": 0.8123,
        }
    ]
    with patch.object(client, "_request_with_retry", return_value=mock_response):
        results = client.search_similarity("attention", k=5)
        assert len(results) == 1
        assert results[0].identifier == "N18-3011"
        assert results[0].similarity == 0.8123
        client._request_with_retry.assert_called_once_with(
            "GET", "/search/similarity", params={"q": "attention", "k": 5}
        )


def test_search_keyword_calls_api_and_maps_results():
    from paperscout.backends.acl_anthology import _ACLAnthologyHTTPClient
    client = _ACLAnthologyHTTPClient()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "id": "N18-3011",
            "title": "Attention Is All You Need",
            "abstract": "",
            "authors": "",
            "venue": "",
            "year": 2017,
            "url": "https://aclanthology.org/N18-3011/",
            "bibtex": "",
            "pdf_url": "",
        }
    ]
    with patch.object(client, "_request_with_retry", return_value=mock_response):
        results = client.search_keyword("attention", limit=5)
        assert len(results) == 1
        assert results[0].identifier == "N18-3011"
        client._request_with_retry.assert_called_once_with(
            "GET", "/search/keyword", params={"q": "attention", "limit": 5}
        )


def test_search_merges_similarity_and_keyword_results():
    from paperscout.backends.acl_anthology import _ACLAnthologyHTTPClient
    client = _ACLAnthologyHTTPClient()

    similarity_response = MagicMock()
    similarity_response.json.return_value = [
        {"id": "A", "title": "A", "authors": "", "venue": "", "year": None, "url": "", "bibtex": "", "pdf_url": "", "score": 0.9},
        {"id": "B", "title": "B", "authors": "", "venue": "", "year": None, "url": "", "bibtex": "", "pdf_url": "", "score": 0.8},
    ]
    keyword_response = MagicMock()
    keyword_response.json.return_value = [
        {"id": "B", "title": "B", "authors": "", "venue": "", "year": None, "url": "", "bibtex": "", "pdf_url": ""},
        {"id": "C", "title": "C", "authors": "", "venue": "", "year": None, "url": "", "bibtex": "", "pdf_url": ""},
    ]

    def fake_request(method, path, **kwargs):
        if path == "/search/similarity":
            return similarity_response
        return keyword_response

    with patch.object(client, "_request_with_retry", side_effect=fake_request):
        results = client.search("query", limit=10)
        ids = [p.identifier for p in results]
        assert ids == ["A", "B", "C"]
        b = [p for p in results if p.identifier == "B"][0]
        assert b.similarity == 0.8  # higher similarity wins


def test_search_truncates_to_limit():
    from paperscout.backends.acl_anthology import _ACLAnthologyHTTPClient
    client = _ACLAnthologyHTTPClient()

    similarity_response = MagicMock()
    similarity_response.json.return_value = [
        {"id": str(i), "title": str(i), "authors": "", "venue": "", "year": None, "url": "", "bibtex": "", "pdf_url": "", "score": 0.5}
        for i in range(10)
    ]
    keyword_response = MagicMock()
    keyword_response.json.return_value = []

    with patch.object(client, "_request_with_retry", side_effect=[similarity_response, keyword_response]):
        results = client.search("query", limit=5)
        assert len(results) == 5


def test_get_paper_returns_paper():
    from paperscout.backends.acl_anthology import _ACLAnthologyHTTPClient
    client = _ACLAnthologyHTTPClient()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "id": "N18-3011",
        "title": "Attention Is All You Need",
        "authors": "",
        "venue": "",
        "year": 2017,
        "url": "https://aclanthology.org/N18-3011/",
        "bibtex": "",
        "pdf_url": "https://aclanthology.org/N18-3011.pdf",
    }
    with patch.object(client, "_request_with_retry", return_value=mock_response):
        paper = client.get_paper("N18-3011")
        assert paper.identifier == "N18-3011"
        client._request_with_retry.assert_called_once_with("GET", "/paper/N18-3011")


def test_get_paper_returns_none_on_404():
    from paperscout.backends.acl_anthology import _ACLAnthologyHTTPClient
    client = _ACLAnthologyHTTPClient()
    with patch.object(client, "_request_with_retry", side_effect=Exception("404")):
        paper = client.get_paper("missing")
        assert paper is None


def test_download_pdf_writes_file(tmp_path):
    from paperscout.backends.acl_anthology import _ACLAnthologyHTTPClient
    client = _ACLAnthologyHTTPClient()
    pdf_url = "https://example.com/paper.pdf"
    save_path = tmp_path / "downloads"
    save_path.mkdir()

    mock_response = MagicMock()
    mock_response.content = b"pdf bytes"
    mock_response.headers = {"content-type": "application/pdf"}

    with patch("requests.get", return_value=mock_response) as mock_get:
        path, filename = client.download_pdf(pdf_url, save_path)
        assert Path(path).exists()
        assert Path(path).read_bytes() == b"pdf bytes"
        mock_get.assert_called_once_with(pdf_url, timeout=client.timeout)


def test_local_backend_inherits_base():
    with patch("paperscout.backends.acl_anthology.ACL_ANTHOLOGY_AVAILABLE", True):
        with patch("paperscout.backends.acl_anthology._ACLAnthologyLocalBackend.__init__", return_value=None):
            from paperscout.backends.acl_anthology import _ACLAnthologyLocalBackend
            backend = _ACLAnthologyLocalBackend()
            from paperscout.backends.base import BaseBackend
            assert isinstance(backend, BaseBackend)


def test_local_backend_search_method_exists():
    with patch("paperscout.backends.acl_anthology.ACL_ANTHOLOGY_AVAILABLE", True):
        with patch("paperscout.backends.acl_anthology._ACLAnthologyLocalBackend.__init__", return_value=None):
            from paperscout.backends.acl_anthology import _ACLAnthologyLocalBackend
            backend = _ACLAnthologyLocalBackend()
            assert hasattr(backend, "search")
            assert callable(getattr(backend, "search"))
            assert hasattr(backend, "download")
            assert callable(getattr(backend, "download"))


def test_facade_uses_http_client_for_search():
    from paperscout.backends.acl_anthology import ACLAnthologyBackend
    backend = ACLAnthologyBackend()
    mock_paper = MagicMock()
    with patch.object(backend, "_http_client") as mock_http:
        mock_http.search.return_value = [mock_paper]
        results = backend.search("attention", limit=5)
        assert results == [mock_paper]
        mock_http.search.assert_called_once_with("attention", limit=5)


def test_facade_falls_back_to_local_on_search_error():
    from paperscout.backends.acl_anthology import ACLAnthologyBackend
    backend = ACLAnthologyBackend()
    backend._local_backend = MagicMock()
    backend._local_backend.search.return_value = []
    with patch.object(backend._http_client, "search", side_effect=Exception("API down")):
        results = backend.search("attention", limit=5)
        assert results == []
        backend._local_backend.search.assert_called_once_with("attention", limit=5)


def test_facade_uses_http_client_for_download():
    from paperscout.backends.acl_anthology import ACLAnthologyBackend
    backend = ACLAnthologyBackend()
    with patch.object(backend, "_http_client") as mock_http:
        mock_http.get_paper.return_value = MagicMock(
            identifier="N18-3011",
            title="Attention Is All You Need",
            authors=["A", "B"],
            pdf_url="https://aclanthology.org/N18-3011.pdf",
        )
        mock_http.download_pdf.return_value = ("/tmp/N18-3011.pdf", "N18-3011.pdf")
        result = backend.download("N18-3011", output_dir="/tmp")
        assert result["status"] == "success"
        mock_http.get_paper.assert_called_once_with("N18-3011")
        mock_http.download_pdf.assert_called_once()


def test_facade_falls_back_to_local_on_download_error():
    from paperscout.backends.acl_anthology import ACLAnthologyBackend
    backend = ACLAnthologyBackend()
    backend._local_backend = MagicMock()
    backend._local_backend.download.return_value = {"status": "success"}
    with patch.object(backend._http_client, "get_paper", side_effect=Exception("API down")):
        result = backend.download("N18-3011", output_dir="/tmp")
        assert result["status"] == "success"
        backend._local_backend.download.assert_called_once_with("N18-3011", output_dir="/tmp")


if __name__ == "__main__":
    unittest.main()
