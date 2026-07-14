# ACL Anthology Backend — HTTP API Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `ACLAnthologyBackend` to call the ACL Anthology Search API at `https://ivykopal-acl-api.hf.space` first, while preserving the existing local `acl-anthology` package as a fallback.

**Architecture:** The backend is split into a private `_ACLAnthologyHTTPClient` that owns all HTTP calls and retry logic, a private `_ACLAnthologyLocalBackend` that wraps the legacy local package, and the public `ACLAnthologyBackend` facade that tries HTTP first and falls back to local on failure. The existing `BaseBackend` interface and `PaperSearcher` consumers remain unchanged.

**Tech Stack:** Python 3.8+, `requests` (already a dependency), standard `logging`, `pytest`, `unittest.mock`.

## Global Constraints

- Python version floor: `>=3.8` (matching `pyproject.toml`).
- Reuse `requests` for HTTP; do not add `httpx` unless the spec changes.
- Default API base URL: `https://ivykopal-acl-api.hf.space`.
- Configurable via constructor arg `base_url` or env var `PAPERSCOUT_ACL_API_URL`.
- Search strategy: similarity first, then keyword, then merge/deduplicate by `id` keeping the higher score.
- HTTP fallback: on any API failure (including `500`), fall back to the local `acl-anthology` backend if installed.
- `503 service not ready`: retry with exponential backoff up to `max_retry_wait` (default cumulative 30 s).
- Keep `acl-anthology` as an optional dependency.
- All existing tests must still pass after each task.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `paperscout/backends/acl_anthology.py` | Contains `_ACLAnthologyHTTPClient`, `_ACLAnthologyLocalBackend`, and the public `ACLAnthologyBackend` facade. |
| `paperscout/backends/base.py` | Unchanged; provides `BaseBackend`. |
| `paperscout/types.py` | Unchanged; provides the `Paper` dataclass and mapping target. |
| `paperscout/search.py` | Unchanged; consumes `ACLAnthologyBackend` via `PaperSearcher.BACKENDS`. |
| `paperscout/download.py` | Unchanged; consumes `ACLAnthologyBackend` via `PaperDownloader._get_backend`. |
| `pyproject.toml` | Move `acl-anthology` to an optional dependency; ensure `requests` remains in core deps. |
| `requirements.txt` | Mirror `pyproject.toml` optional-dependency story if needed. |
| `tests/test_backends.py` | Update/expand tests for HTTP path, local fallback, retry behavior, and result mapping. |

---

### Task 1: HTTP client skeleton and base URL resolution

**Files:**
- Modify: `paperscout/backends/acl_anthology.py`
- Test: `tests/test_backends.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `_ACLAnthologyHTTPClient` with `__init__(self, base_url=None, timeout=30.0, max_retry_wait=30.0)` and `health(self)` method.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_backends.py::test_http_client_base_url_defaults_to_hf_space tests/test_backends.py::test_http_client_base_url_respects_env_var tests/test_backends.py::test_http_client_base_url_constructor_wins_over_env_var tests/test_backends.py::test_http_client_strips_trailing_slash -v`

Expected: FAIL with `ImportError` or `AttributeError` for `_ACLAnthologyHTTPClient`.

- [ ] **Step 3: Write minimal implementation**

In `paperscout/backends/acl_anthology.py`, at the top of the module after imports, add:

```python
import logging
import os

logger = logging.getLogger(__name__)


DEFAULT_ACL_API_URL = "https://ivykopal-acl-api.hf.space"


class _ACLAnthologyHTTPClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        max_retry_wait: float = 30.0,
    ):
        resolved = base_url or os.environ.get("PAPERSCOUT_ACL_API_URL") or DEFAULT_ACL_API_URL
        self.base_url = resolved.rstrip("/")
        self.timeout = timeout
        self.max_retry_wait = max_retry_wait

    def health(self) -> dict:
        import requests
        response = requests.get(f"{self.base_url}/health", timeout=self.timeout)
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backends.py::test_http_client_base_url_defaults_to_hf_space tests/test_backends.py::test_http_client_base_url_respects_env_var tests/test_backends.py::test_http_client_base_url_constructor_wins_over_env_var tests/test_backends.py::test_http_client_strips_trailing_slash -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperscout/backends/acl_anthology.py tests/test_backends.py
git commit -m "feat: add ACL Anthology HTTP client skeleton and base URL resolution

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 503 retry utility

**Files:**
- Modify: `paperscout/backends/acl_anthology.py`
- Test: `tests/test_backends.py`

**Interfaces:**
- Consumes: `_ACLAnthologyHTTPClient.base_url`, `timeout`, `max_retry_wait`.
- Produces: `_ACLAnthologyHTTPClient._request_with_retry(self, method, path, **kwargs)` that returns a `requests.Response`.

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import MagicMock, patch


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_backends.py::test_request_with_retry_succeeds_immediately tests/test_backends.py::test_request_with_retry_retries_on_503_then_succeeds tests/test_backends.py::test_request_with_retry_gives_up_after_max_wait -v`

Expected: FAIL with `AttributeError` for `_request_with_retry`.

- [ ] **Step 3: Write minimal implementation**

Add inside `_ACLAnthologyHTTPClient`:

```python
    def _request_with_retry(
        self,
        method: str,
        path: str,
        **kwargs,
    ):
        import requests
        import time

        url = f"{self.base_url}{path}"
        kwargs.setdefault("timeout", self.timeout)

        delay = 1.0
        total_wait = 0.0
        while True:
            response = requests.request(method, url, **kwargs)
            if response.status_code == 503:
                logger.debug("Got 503 from %s, retrying after %.1fs", url, delay)
                time.sleep(delay)
                total_wait += delay
                delay *= 2
                if total_wait >= self.max_retry_wait:
                    response.raise_for_status()
                continue
            response.raise_for_status()
            return response
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backends.py::test_request_with_retry_succeeds_immediately tests/test_backends.py::test_request_with_retry_retries_on_503_then_succeeds tests/test_backends.py::test_request_with_retry_gives_up_after_max_wait -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperscout/backends/acl_anthology.py tests/test_backends.py
git commit -m "feat: add 503 retry utility to ACL Anthology HTTP client

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: API response to `Paper` mapping

**Files:**
- Modify: `paperscout/backends/acl_anthology.py`
- Test: `tests/test_backends.py`

**Interfaces:**
- Consumes: `paperscout.types.Paper`.
- Produces: `_ACLAnthologyHTTPClient._paper_from_api(self, data: dict, similarity: Optional[float] = None) -> Paper`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_backends.py::test_paper_from_api_maps_all_fields tests/test_backends.py::test_paper_from_api_handles_null_year_and_empty_fields -v`

Expected: FAIL with `AttributeError` for `_paper_from_api`.

- [ ] **Step 3: Write minimal implementation**

Add inside `_ACLAnthologyHTTPClient`:

```python
    def _paper_from_api(
        self,
        data: dict,
        similarity: Optional[float] = None,
    ) -> Paper:
        authors_raw = data.get("authors", "") or ""
        authors = [a.strip() for a in authors_raw.split(",") if a.strip()]

        venue = data.get("venue", "") or ""
        categories = [venue] if venue else []

        year = data.get("year")
        if year is not None:
            year = int(year)

        return Paper(
            title=(data.get("title", "") or "").strip(),
            authors=authors,
            year=year,
            abstract=(data.get("abstract", "") or "").strip(),
            source="acl_anthology",
            identifier=(data.get("id", "") or "").strip(),
            url=(data.get("url", "") or "").strip(),
            pdf_url=(data.get("pdf_url", "") or "").strip(),
            published="",
            categories=categories,
            similarity=similarity,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backends.py::test_paper_from_api_maps_all_fields tests/test_backends.py::test_paper_from_api_handles_null_year_and_empty_fields -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperscout/backends/acl_anthology.py tests/test_backends.py
git commit -m "feat: map ACL Anthology API responses to internal Paper type

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: Keyword and similarity search endpoints

**Files:**
- Modify: `paperscout/backends/acl_anthology.py`
- Test: `tests/test_backends.py`

**Interfaces:**
- Consumes: `_request_with_retry`, `_paper_from_api`.
- Produces: `_ACLAnthologyHTTPClient.search_keyword(self, query: str, limit: int = 10) -> List[Paper]` and `_ACLAnthologyHTTPClient.search_similarity(self, query: str, k: int = 10) -> List[Paper]`.

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import MagicMock, patch


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_backends.py::test_search_similarity_calls_api_and_maps_results tests/test_backends.py::test_search_keyword_calls_api_and_maps_results -v`

Expected: FAIL with `AttributeError` for `search_similarity` / `search_keyword`.

- [ ] **Step 3: Write minimal implementation**

Add inside `_ACLAnthologyHTTPClient`:

```python
    def search_similarity(self, query: str, k: int = 10) -> List[Paper]:
        response = self._request_with_retry(
            "GET",
            "/search/similarity",
            params={"q": query, "k": k},
        )
        data = response.json()
        return [self._paper_from_api(item, similarity=item.get("score")) for item in data]

    def search_keyword(self, query: str, limit: int = 10) -> List[Paper]:
        response = self._request_with_retry(
            "GET",
            "/search/keyword",
            params={"q": query, "limit": limit},
        )
        data = response.json()
        return [self._paper_from_api(item) for item in data]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backends.py::test_search_similarity_calls_api_and_maps_results tests/test_backends.py::test_search_keyword_calls_api_and_maps_results -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperscout/backends/acl_anthology.py tests/test_backends.py
git commit -m "feat: add keyword and similarity search endpoints to HTTP client

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: Merge and deduplicate combined search results

**Files:**
- Modify: `paperscout/backends/acl_anthology.py`
- Test: `tests/test_backends.py`

**Interfaces:**
- Consumes: `search_similarity`, `search_keyword`, `_paper_from_api`.
- Produces: `_ACLAnthologyHTTPClient.search(self, query: str, limit: int = 10) -> List[Paper]` that runs similarity first, then keyword, merges by `id`, and truncates to `limit`.

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import MagicMock, patch


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_backends.py::test_search_merges_similarity_and_keyword_results tests/test_backends.py::test_search_truncates_to_limit -v`

Expected: FAIL with `AttributeError` for `search`.

- [ ] **Step 3: Write minimal implementation**

Add inside `_ACLAnthologyHTTPClient`:

```python
    def search(self, query: str, limit: int = 10) -> List[Paper]:
        similarity_results = self.search_similarity(query, k=limit)
        keyword_results = self.search_keyword(query, limit=limit)

        merged: Dict[str, Paper] = {}
        for paper in similarity_results + keyword_results:
            existing = merged.get(paper.identifier)
            if existing is None or (paper.similarity or 0) > (existing.similarity or 0):
                merged[paper.identifier] = paper

        results = list(merged.values())
        results.sort(key=lambda p: p.similarity or 0, reverse=True)
        return results[:limit]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backends.py::test_search_merges_similarity_and_keyword_results tests/test_backends.py::test_search_truncates_to_limit -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperscout/backends/acl_anthology.py tests/test_backends.py
git commit -m "feat: merge and deduplicate similarity and keyword search results

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: Paper lookup and PDF download

**Files:**
- Modify: `paperscout/backends/acl_anthology.py`
- Test: `tests/test_backends.py`

**Interfaces:**
- Consumes: `_request_with_retry`, `_paper_from_api`.
- Produces: `_ACLAnthologyHTTPClient.get_paper(self, paper_id: str) -> Optional[Paper]` and `_ACLAnthologyHTTPClient.download_pdf(self, pdf_url: str, save_path: Path) -> Tuple[str, str]`.

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
from unittest.mock import MagicMock, patch


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_backends.py::test_get_paper_returns_paper tests/test_backends.py::test_get_paper_returns_none_on_404 tests/test_backends.py::test_download_pdf_writes_file -v`

Expected: FAIL with `AttributeError` for `get_paper` / `download_pdf`.

- [ ] **Step 3: Write minimal implementation**

Add inside `_ACLAnthologyHTTPClient`:

```python
    def get_paper(self, paper_id: str) -> Optional[Paper]:
        try:
            response = self._request_with_retry("GET", f"/paper/{paper_id}")
        except Exception:
            return None
        return self._paper_from_api(response.json())

    def download_pdf(self, pdf_url: str, save_dir: Path) -> Tuple[str, str]:
        import requests
        response = requests.get(pdf_url, timeout=self.timeout)
        response.raise_for_status()

        # Derive filename from URL path; fall back to 'paper.pdf'
        from urllib.parse import urlparse
        parsed = urlparse(pdf_url)
        filename = Path(parsed.path).name or "paper.pdf"
        if not filename.endswith(".pdf"):
            filename += ".pdf"

        save_dir.mkdir(parents=True, exist_ok=True)
        path = save_dir / filename
        path.write_bytes(response.content)
        return str(path), filename
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backends.py::test_get_paper_returns_paper tests/test_backends.py::test_get_paper_returns_none_on_404 tests/test_backends.py::test_download_pdf_writes_file -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperscout/backends/acl_anthology.py tests/test_backends.py
git commit -m "feat: add paper lookup and PDF download to HTTP client

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: Extract local backend into a private class

**Files:**
- Modify: `paperscout/backends/acl_anthology.py`
- Test: `tests/test_backends.py`

**Interfaces:**
- Consumes: existing `acl-anthology` package logic.
- Produces: `_ACLAnthologyLocalBackend` with `search(self, query, limit=10) -> List[Paper]` and `download(self, identifier, **kwargs) -> Dict`.

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import patch


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_backends.py::test_local_backend_inherits_base tests/test_backends.py::test_local_backend_search_method_exists -v`

Expected: FAIL with `ImportError` for `_ACLAnthologyLocalBackend`.

- [ ] **Step 3: Write minimal implementation**

Rename the existing `ACLAnthologyBackend` class to `_ACLAnthologyLocalBackend`. Keep all current local search/download/format logic intact. Then add a temporary public `ACLAnthologyBackend` class that delegates to `_ACLAnthologyLocalBackend` so existing tests and consumers keep working between tasks.

```python
class _ACLAnthologyLocalBackend(BaseBackend):
    """Legacy local ACL Anthology backend using the acl-anthology package."""

    name: str = "acl_anthology_local"
    supported_sources: List[str] = ["acl_anthology", "acl", "anthology"]

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key)
        if not ACL_ANTHOLOGY_AVAILABLE:
            raise ImportError(
                "acl-anthology is not installed. Install it with: pip install acl-anthology"
            )
        self.client = Anthology.from_repo()
        self.download_dir = Path(tempfile.gettempdir()) / "paperscout" / "acl_anthology"
        self.download_dir.mkdir(parents=True, exist_ok=True)

    # ... keep the existing search, _search, download, _format_result,
    # _parse_authors, _parse_pdf_url, download_by_doi, _download_file methods
    # exactly as they are in the current ACLAnthologyBackend class.


class ACLAnthologyBackend(BaseBackend):
    """Backward-compatible wrapper around the local backend (replaced in Task 8)."""

    name: str = "acl_anthology"
    supported_sources: List[str] = ["acl_anthology", "acl", "anthology"]

    def __init__(self, api_key: Optional[str] = None, **_kwargs):
        super().__init__(api_key)
        self._local = _ACLAnthologyLocalBackend(api_key)

    def search(self, query: str, limit: int = 10) -> List[Paper]:
        return self._local.search(query, limit=limit)

    def download(self, identifier: str, **kwargs) -> Dict:
        return self._local.download(identifier, **kwargs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backends.py::test_local_backend_inherits_base tests/test_backends.py::test_local_backend_search_method_exists -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperscout/backends/acl_anthology.py tests/test_backends.py
git commit -m "refactor: extract local ACL Anthology backend into private class

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: Wire the public facade with HTTP-first and local fallback

**Files:**
- Modify: `paperscout/backends/acl_anthology.py`
- Test: `tests/test_backends.py`

**Interfaces:**
- Consumes: `_ACLAnthologyHTTPClient`, `_ACLAnthologyLocalBackend`.
- Produces: `ACLAnthologyBackend` public class with `search(self, query, limit=10) -> List[Paper]` and `download(self, identifier, **kwargs) -> Dict`, plus `__init__(self, api_key=None, base_url=None, timeout=30.0, max_retry_wait=30.0)`.

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import MagicMock, patch


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_backends.py::test_facade_uses_http_client_for_search tests/test_backends.py::test_facade_falls_back_to_local_on_search_error tests/test_backends.py::test_facade_uses_http_client_for_download tests/test_backends.py::test_facade_falls_back_to_local_on_download_error -v`

Expected: FAIL with `AttributeError` for new facade behavior.

- [ ] **Step 3: Write minimal implementation**

Replace the temporary backward-compatible `ACLAnthologyBackend` wrapper from Task 7 with the new HTTP-first facade:

```python
class ACLAnthologyBackend(BaseBackend):
    """Public facade for ACL Anthology: tries HTTP API first, falls back to local package."""

    name: str = "acl_anthology"
    supported_sources: List[str] = ["acl_anthology", "acl", "anthology"]

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        max_retry_wait: float = 30.0,
    ):
        super().__init__(api_key)
        self._http_client = _ACLAnthologyHTTPClient(
            base_url=base_url,
            timeout=timeout,
            max_retry_wait=max_retry_wait,
        )
        self._local_backend: Optional[_ACLAnthologyLocalBackend] = None
        if ACL_ANTHOLOGY_AVAILABLE:
            try:
                self._local_backend = _ACLAnthologyLocalBackend(api_key)
            except Exception as e:
                logger.warning("Failed to initialize local ACL Anthology backend: %s", e)

    def search(self, query: str, limit: int = 10) -> List[Paper]:
        try:
            return self._http_client.search(query, limit=limit)
        except Exception as e:
            logger.warning("ACL Anthology API search failed (%s), trying local fallback.", e)
            if self._local_backend is not None:
                return self._local_backend.search(query, limit=limit)
            logger.warning("No local ACL Anthology backend available.")
            return []

    def download(self, identifier: str, **kwargs) -> Dict:
        output_dir = kwargs.get("output_dir")
        try:
            paper = self._http_client.get_paper(identifier)
            if paper is not None and paper.pdf_url:
                from pathlib import Path
                save_dir = Path(output_dir) if output_dir else Path(tempfile.gettempdir()) / "paperscout" / "acl_anthology"
                path, filename = self._http_client.download_pdf(paper.pdf_url, save_dir)
                return {
                    "status": "success",
                    "identifier": identifier,
                    "path": path,
                    "filename": filename,
                    "title": paper.title,
                    "authors": paper.authors,
                    "source": "acl_anthology",
                }
        except Exception as e:
            logger.warning("ACL Anthology API download failed (%s), trying local fallback.", e)

        if self._local_backend is not None:
            return self._local_backend.download(identifier, **kwargs)

        return {
            "status": "error",
            "message": f"Failed to download {identifier} from ACL Anthology API and no local backend is available.",
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backends.py::test_facade_uses_http_client_for_search tests/test_backends.py::test_facade_falls_back_to_local_on_search_error tests/test_backends.py::test_facade_uses_http_client_for_download tests/test_backends.py::test_facade_falls_back_to_local_on_download_error -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperscout/backends/acl_anthology.py tests/test_backends.py
git commit -m "feat: wire ACL Anthology HTTP-first facade with local fallback

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 9: Update existing backend tests for the new facade

**Files:**
- Modify: `tests/test_backends.py`

**Interfaces:**
- Consumes: `ACLAnthologyBackend` public facade.
- Produces: updated `TestACLAnthologyBackend` tests that mock the HTTP client or local backend as appropriate.

- [ ] **Step 1: Write the failing test**

Update the existing `TestACLAnthologyBackend` class in `tests/test_backends.py`:

```python
class TestACLAnthologyBackend(unittest.TestCase):
    """Test cases for ACLAnthologyBackend."""

    def test_acl_backend_inherits_base(self):
        """Test that ACLAnthologyBackend inherits from BaseBackend."""
        with patch("paperscout.backends.acl_anthology.ACL_ANTHOLOGY_AVAILABLE", True):
            with patch.object(ACLAnthologyBackend, "__init__", return_value=None):
                backend = ACLAnthologyBackend()
                backend._http_client = None
                backend._local_backend = None
                self.assertIsInstance(backend, BaseBackend)

    def test_acl_backend_search_method_exists(self):
        """Test that ACLAnthologyBackend has a search method."""
        with patch("paperscout.backends.acl_anthology.ACL_ANTHOLOGY_AVAILABLE", True):
            with patch.object(ACLAnthologyBackend, "__init__", return_value=None):
                backend = ACLAnthologyBackend()
                self.assertTrue(hasattr(backend, "search"))
                self.assertTrue(callable(getattr(backend, "search")))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_backends.py::TestACLAnthologyBackend -v`

Expected: FAIL because the old tests reference the old init signature.

- [ ] **Step 3: Write minimal implementation**

Replace the old `TestACLAnthologyBackend` class contents with the updated tests above. Remove any old tests that directly instantiate `ACLAnthologyBackend()` without mocking (they would try to load the anthology).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backends.py::TestACLAnthologyBackend -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_backends.py
git commit -m "test: update ACL Anthology backend tests for HTTP facade

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 10: Update dependency metadata

**Files:**
- Modify: `pyproject.toml`
- Modify: `requirements.txt`
- Test: `python -c "import paperscout.backends.acl_anthology; print('ok')"`

**Interfaces:**
- Consumes: existing dependency declarations.
- Produces: `acl-anthology` stays optional; `requests` stays core.

- [ ] **Step 1: Write the failing test**

No automated test. Instead, verify the import works without `acl-anthology` installed:

```bash
python -c "import paperscout.backends.acl_anthology; print('import ok')"
```

Expected: should print `import ok` even if `acl-anthology` is not installed.

- [ ] **Step 2: Run test to verify it fails (or passes)**

Run: `python -c "import paperscout.backends.acl_anthology; print('import ok')"`

Expected: currently likely passes because `ACL_ANTHOLOGY_AVAILABLE` is already guarded. If it fails, fix the import guards.

- [ ] **Step 3: Write minimal implementation**

In `pyproject.toml`:

```toml
[project.optional-dependencies]
arxiv = ["arxivy>=0.1.0"]
dblp = ["dblpcli>=0.1.0"]
semantic_scholar = ["s2cli>=0.1.0"]
acl_anthology = ["acl-anthology>=1.2.0"]
all = [
    "arxivy>=0.1.0",
    "dblpcli>=0.1.0",
    "s2cli>=0.1.0",
    "acl-anthology>=1.2.0",
]
```

Core dependencies must still include `requests>=2.28.0` (already present).

In `requirements.txt`, ensure `requests` is under core deps and `acl-anthology` is listed as an optional backend dep (it already is). No change needed unless you want to add a comment clarifying optionality.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -c "import paperscout.backends.acl_anthology; print('import ok')"`

Expected: `import ok`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml requirements.txt
git commit -m "build: keep acl-anthology optional and requests core for HTTP backend

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 11: Run full test suite and manual verification

**Files:**
- All modified files.

**Interfaces:**
- Consumes: complete implementation.
- Produces: passing tests and verified CLI behavior.

- [ ] **Step 1: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Manual CLI verification**

```bash
paperscout search "attention is all you need" --source acl_anthology
paperscout download N18-3011
```

Expected: search returns results; download succeeds and writes a PDF to `./downloads`.

- [ ] **Step 3: Verify fallback behavior**

Temporarily break the base URL (e.g., set `PAPERSCOUT_ACL_API_URL=http://localhost:1`) and rerun search. With `acl-anthology` installed, it should fall back to local results. Without it installed, it should return an empty list gracefully.

```bash
PAPERSCOUT_ACL_API_URL=http://localhost:1 paperscout search "attention is all you need" --source acl_anthology
```

- [ ] **Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "fix: address issues found during full test and manual verification

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**

| Spec Section | Task(s) |
|--------------|---------|
| HTTP client skeleton + base URL | Task 1 |
| 503 retry with backoff | Task 2 |
| API-to-`Paper` mapping | Task 3 |
| Similarity + keyword search | Task 4 |
| Merge/deduplicate | Task 5 |
| Download via `/paper/{id}` | Task 6 |
| Local backend extraction | Task 7 |
| HTTP-first facade with local fallback | Task 8 |
| Dependency updates | Task 10 |
| Test coverage | Tasks 1–9, 11 |
| Manual verification | Task 11 |

**Placeholder scan:**

- No `TBD`, `TODO`, or vague steps.
- Every step includes concrete code, commands, and expected output.
- No "add appropriate error handling" without specifics.

**Type consistency:**

- `_ACLAnthologyHTTPClient.search*` returns `List[Paper]`.
- `_ACLAnthologyHTTPClient.get_paper` returns `Optional[Paper]`.
- `ACLAnthologyBackend.search` and `download` signatures match `BaseBackend`.
- `download_pdf` accepts `Path` and returns `Tuple[str, str]`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-14-acl-anthology-api-plan.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using `executing-plans`, batch execution with checkpoints.

Which approach would you like?
