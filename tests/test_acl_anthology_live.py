"""Live integration test for the ACL Anthology HTTP API client.

These tests hit the real deployed service (https://ivykopal-acl-api.hf.space by
default) and exercise the real `_ACLAnthologyHTTPClient` / `ACLAnthologyBackend`
code — not mocks. They are skipped unless explicitly opted in AND the service
is reachable, so the default `pytest` run stays fast and offline.

Run explicitly:

    PAPERSCOUT_RUN_LIVE_TESTS=1 \\
        python3 -m pytest tests/test_acl_anthology_live.py -v -s

To target a local dev server instead:

    PAPERSCOUT_RUN_LIVE_TESTS=1 PAPERSCOUT_ACL_API_URL=http://localhost:8000 \\
        python3 -m pytest tests/test_acl_anthology_live.py -v -s
"""

import os
from pathlib import Path

import pytest
import requests

from paperscout.backends.acl_anthology import (
    ACL_ANTHOLOGY_AVAILABLE,
    ACLAnthologyBackend,
    DEFAULT_ACL_API_URL,
    _ACLAnthologyHTTPClient,
    _ACLAnthologyLocalBackend,
)
from paperscout.types import Paper


BASE_URL = os.environ.get("PAPERSCOUT_ACL_API_URL") or DEFAULT_ACL_API_URL
_OPT_IN = os.environ.get("PAPERSCOUT_RUN_LIVE_TESTS", "") == "1"


def _service_ready() -> bool:
    """Return True iff the service is reachable and reports ready."""
    if not _OPT_IN:
        return False
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=10)
    except requests.RequestException:
        return False
    if r.status_code != 200:
        return False
    try:
        return r.json().get("status") == "ok"
    except ValueError:
        return False


pytestmark = pytest.mark.skipif(
    not _service_ready(),
    reason=(
        "set PAPERSCOUT_RUN_LIVE_TESTS=1 (and ensure the API is ready) "
        f"to run live ACL Anthology tests against {BASE_URL}"
    ),
)


# ---------------------------------------------------------------------------
# Health / readiness
# ---------------------------------------------------------------------------

def test_health_reports_ready_with_index_size():
    client = _ACLAnthologyHTTPClient(base_url=BASE_URL)
    health = client.health()
    assert health["status"] == "ok"
    assert isinstance(health["index_size"], int)
    assert health["index_size"] > 100_000  # full corpus (~128k)
    assert "last_synced_at" in health


# ---------------------------------------------------------------------------
# Similarity search
# ---------------------------------------------------------------------------

def test_search_similarity_returns_ranked_papers():
    client = _ACLAnthologyHTTPClient(base_url=BASE_URL)
    results = client.search_similarity("attention mechanism for transformers", k=5)
    assert len(results) == 5
    assert all(isinstance(p, Paper) for p in results)
    # Scores are cosine similarity in [-1, 1] and should be descending.
    scores = [p.similarity for p in results]
    assert all(-1.0 <= s <= 1.0 for s in scores)
    assert scores == sorted(scores, reverse=True)
    # Every result must carry core metadata.
    for p in results:
        assert p.source == "acl_anthology"
        assert p.identifier
        assert p.title


def test_search_similarity_score_matches_raw_api():
    """The client's mapped score must equal the raw `score` field from the API."""
    client = _ACLAnthologyHTTPClient(base_url=BASE_URL)
    raw = requests.get(
        f"{BASE_URL}/search/similarity", params={"q": "neural machine translation", "k": 3}, timeout=30
    ).json()
    mapped = client.search_similarity("neural machine translation", k=3)
    assert len(raw) == len(mapped) == 3
    for raw_item, paper in zip(raw, mapped):
        assert raw_item["id"] == paper.identifier
        assert abs(raw_item["score"] - paper.similarity) < 1e-9


# ---------------------------------------------------------------------------
# Keyword search
# ---------------------------------------------------------------------------

def test_search_keyword_returns_bm25_results():
    client = _ACLAnthologyHTTPClient(base_url=BASE_URL)
    results = client.search_keyword("transformer attention", limit=5)
    assert len(results) == 5
    for p in results:
        assert isinstance(p, Paper)
        assert p.identifier
        assert p.title
    # Keyword results have no similarity score from the API.
    assert all(p.similarity is None for p in results)


def test_search_keyword_empty_query_yields_no_match():
    client = _ACLAnthologyHTTPClient(base_url=BASE_URL)
    results = client.search_keyword("zzqxqzxznonexistentterm", limit=5)
    assert results == []


# ---------------------------------------------------------------------------
# Merged search
# ---------------------------------------------------------------------------

def test_search_merges_and_dedups_within_limit():
    client = _ACLAnthologyHTTPClient(base_url=BASE_URL)
    limit = 8
    results = client.search("semantic parsing", limit=limit)
    assert 0 < len(results) <= limit
    # No duplicate identifiers after merge.
    ids = [p.identifier for p in results]
    assert len(ids) == len(set(ids))
    # Results are sorted by similarity descending.
    sims = [p.similarity or 0 for p in results]
    assert sims == sorted(sims, reverse=True)


# ---------------------------------------------------------------------------
# Paper lookup
# ---------------------------------------------------------------------------

KNOWN_PAPER_ID = "N18-3011"  # "Attention Is All You Need"


def test_get_paper_returns_known_paper():
    client = _ACLAnthologyHTTPClient(base_url=BASE_URL)
    paper = client.get_paper(KNOWN_PAPER_ID)
    assert paper is not None
    assert paper.identifier == KNOWN_PAPER_ID
    assert paper.title
    assert paper.pdf_url
    assert paper.pdf_url.endswith(".pdf")
    assert paper.source == "acl_anthology"


def test_get_paper_returns_none_for_unknown_id():
    client = _ACLAnthologyHTTPClient(base_url=BASE_URL)
    assert client.get_paper("ZZ99-9999") is None


# ---------------------------------------------------------------------------
# PDF download
# ---------------------------------------------------------------------------

def test_download_pdf_writes_valid_bytes(tmp_path):
    client = _ACLAnthologyHTTPClient(base_url=BASE_URL)
    paper = client.get_paper(KNOWN_PAPER_ID)
    assert paper is not None and paper.pdf_url

    path, filename = client.download_pdf(paper.pdf_url, tmp_path)
    written = Path(path)
    assert written.exists()
    assert filename.endswith(".pdf")
    data = written.read_bytes()
    # ACL PDFs are well over 50KB; a %PDF header confirms it's actually a PDF.
    assert data[:4] == b"%PDF"
    assert len(data) > 50_000


# ---------------------------------------------------------------------------
# Facade backend
# ---------------------------------------------------------------------------

def test_facade_search_routes_to_http_api():
    backend = ACLAnthologyBackend(base_url=BASE_URL)
    results = backend.search("machine translation", limit=5)
    assert results
    for p in results:
        assert isinstance(p, Paper)
        assert p.source == "acl_anthology"


def test_facade_download_through_http_api(tmp_path):
    backend = ACLAnthologyBackend(base_url=BASE_URL)
    result = backend.download(KNOWN_PAPER_ID, output_dir=str(tmp_path))
    assert result["status"] == "success"
    assert result["identifier"] == KNOWN_PAPER_ID
    written = Path(result["path"])
    assert written.exists()
    assert written.read_bytes()[:4] == b"%PDF"


def test_facade_download_unknown_paper_reports_error(tmp_path):
    backend = ACLAnthologyBackend(base_url=BASE_URL)
    result = backend.download("ZZ99-9999", output_dir=str(tmp_path))
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# Local fallback (only if the acl-anthology package is installed)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not ACL_ANTHOLOGY_AVAILABLE, reason="acl-anthology package not installed")
def test_local_backend_search_returns_results():
    backend = _ACLAnthologyLocalBackend()
    results = backend.search("attention", limit=3)
    assert results
    for p in results:
        assert isinstance(p, Paper)
        assert p.source == "acl_anthology"
