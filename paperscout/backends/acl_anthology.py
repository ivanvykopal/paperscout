"""
ACL Anthology backend using the acl-anthology package.

ACL Anthology is the premier repository of computational linguistics
papers, covering venues like ACL, EMNLP, NAACL, and more.
"""

import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from paperscout.backends.base import BaseBackend
from paperscout.similarity import _title_similarity
from paperscout.types import Paper

logger = logging.getLogger(__name__)


DEFAULT_ACL_API_URL = "https://ivykopal-acl-api.hf.space"

# Old-style Anthology ID prefixes (e.g. "N19-1423") mapped to venue names.
_OLD_ACL_PREFIXES = {
    "P": "ACL",
    "D": "EMNLP",
    "N": "NAACL",
    "E": "EACL",
    "Q": "TACL",
    "J": "Computational Linguistics",
    "C": "COLING",
    "K": "CoNLL",
    "L": "LREC",
    "S": "SemEval",
    "W": "Workshop",
}


def _venue_from_acl_id(paper_id: str, fallback: str = "") -> str:
    """Derive a venue name from an ACL Anthology ID.

    New-style IDs encode the volume ("2024.findings-naacl.294" -> "findings-naacl"),
    old-style IDs encode it in the letter prefix ("N19-1423" -> "NAACL").
    The API's own venue field is often only "Findings", which loses the conference.
    """
    match = re.match(r"^\d{4}\.([a-z0-9\-]+)\.\d+$", paper_id or "")
    if match:
        return match.group(1)
    match = re.match(r"^([A-Z])\d{2}-\d{4}$", paper_id or "")
    if match and match.group(1) in _OLD_ACL_PREFIXES:
        return _OLD_ACL_PREFIXES[match.group(1)]
    return fallback



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
        response = requests.get(f"{self.base_url}/health", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _request_with_retry(
        self,
        method: str,
        path: str,
        **kwargs,
    ):
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

    def _paper_from_api(
        self,
        data: dict,
        similarity: Optional[float] = None,
    ) -> Paper:
        authors_raw = data.get("authors", "") or ""
        authors = [a.strip() for a in authors_raw.split(",") if a.strip()]

        venue = (data.get("venue", "") or "").strip()
        paper_id = (data.get("id", "") or "").strip()
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
            venue=_venue_from_acl_id(paper_id, venue) or None,
        )

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

    def get_paper(self, paper_id: str) -> Optional[Paper]:
        try:
            response = self._request_with_retry("GET", f"/paper/{paper_id}")
        except Exception:
            return None
        return self._paper_from_api(response.json())

    def download_pdf(self, pdf_url: str, save_dir: Path) -> Tuple[str, str]:
        response = requests.get(pdf_url, timeout=self.timeout)
        response.raise_for_status()

        # Derive filename from URL path; fall back to 'paper.pdf'
        parsed = urlparse(pdf_url)
        filename = Path(parsed.path).name or "paper.pdf"
        if not filename.endswith(".pdf"):
            filename += ".pdf"

        save_dir.mkdir(parents=True, exist_ok=True)
        path = save_dir / filename
        path.write_bytes(response.content)
        return str(path), filename


try:
    from acl_anthology import Anthology
    ACL_ANTHOLOGY_AVAILABLE = True
except ImportError:
    ACL_ANTHOLOGY_AVAILABLE = False


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

    def search(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Paper]:
        """
        Search for papers in ACL Anthology.

        Args:
            query: Search query string (paper title).
            limit: Maximum number of results to return.

        Returns:
            List of Paper objects.
        """
        # Search by iterating through all papers and filtering by title
        results = self._search(query, limit=limit)

        return [self._format_result(paper, similarity) for paper, similarity in results]

    def _search(self, query: str, limit: int = 10) -> List[Tuple[Any, float]]:
        """
        Search ACL Anthology papers by title or abstract.

        Since acl-anthology doesn't have native search, we iterate through all papers
        and filter by title similarity or abstract keyword match.

        Args:
            query: Search query string (title or abstract keyword).
            limit: Maximum number of results to return.

        Returns:
            List of (paper, similarity) tuples sorted by relevance.
        """
        # Collect papers that match the query
        matching_papers = []

        # Iterate through all papers in the anthology
        for paper in self.client.papers():
            paper_title = str(getattr(paper, 'title', ''))
            paper_abstract = str(getattr(paper, 'abstract', ''))

            query_lower = query.lower()
            title_lower = paper_title.lower()
            abstract_lower = paper_abstract.lower()

            similarity = 0.0

            # Check for exact match first
            if query_lower == title_lower:
                similarity = 1.0
            else:
                query_tokens = set(query_lower.split())
                title_tokens = set(title_lower.split())

                if query_tokens == title_tokens:
                    similarity = 1.0
                elif query_tokens.issubset(title_tokens) and len(query_tokens) >= 2:
                    similarity = 0.9
                else:
                    if query_lower in abstract_lower:
                        similarity = 0.7
                    else:
                        similarity = _title_similarity(query, paper_title)

            if similarity > 0.0:  # Include all matches
                matching_papers.append((paper, similarity))

        # Sort by similarity (highest first)
        matching_papers.sort(key=lambda x: x[1], reverse=True)

        # Store the total number of matches before truncation
        self._last_total = len(matching_papers)

        # Return top results with similarity scores
        return matching_papers[:limit]

    def download(self, identifier: str, **kwargs) -> Dict:
        """
        Download a paper from ACL Anthology.

        Args:
            identifier: ACL Anthology paper ID (e.g., 'P18-1001').
            **kwargs:
                - output_dir: Directory to save the PDF.

        Returns:
            Dictionary with download information including path.
        """
        output_dir = kwargs.get("output_dir", str(self.download_dir))
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Get paper by ID
        try:
            paper = self.client.get(identifier)
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to retrieve paper {identifier}: {str(e)}",
            }

        if not paper:
            return {
                "status": "error",
                "message": f"Paper with ID {identifier} not found in ACL Anthology.",
            }

        # Download PDF - resolve PDF URL from paper.pdf or web_url
        pdf_url = self._parse_pdf_url(paper)
        if not pdf_url:
            return {
                "status": "error",
                "message": f"No PDF URL found for paper {identifier}.",
            }

        path, filename = self._download_file(pdf_url, identifier, output_path)

        return {
            "status": "success",
            "identifier": identifier,
            "path": path,
            "filename": filename,
            "title": paper.title if hasattr(paper, 'title') else "",
            "authors": paper.authors if hasattr(paper, 'authors') else [],
        }

    def _format_result(self, paper: Any, similarity: float = 0.0) -> Paper:
        """
        Format ACL Anthology paper to standard format.

        Args:
            paper: Raw paper object from acl-anthology.
            similarity: Relevance score calculated during search.

        Returns:
            Paper object.
        """
        def _get_str_attr(obj: Any, name: str, default: str = "") -> str:
            """Get a string attribute from an object, handling MarkupText and other types."""
            value = getattr(obj, name, default)
            if value is None:
                return default
            return str(value)

        paper_id = _get_str_attr(paper, 'full_id', '') or _get_str_attr(paper, 'id', '')
        venue = _get_str_attr(paper, 'venue', '')
        return Paper(
            title=_get_str_attr(paper, 'title', '').strip(),
            authors=self._parse_authors(getattr(paper, 'authors', [])),
            year=int(getattr(paper, 'year', 0)) if getattr(paper, 'year') else None,
            abstract=_get_str_attr(paper, 'abstract', '').strip() if hasattr(paper, 'abstract') else "",
            source="acl_anthology",
            identifier=paper_id,
            url=_get_str_attr(paper, 'web_url', ''),
            pdf_url=self._parse_pdf_url(paper),
            published=_get_str_attr(paper, 'ingest_date', ''),
            categories=[venue] if venue else [],
            similarity=similarity if similarity > 0 else None,
            venue=_venue_from_acl_id(paper_id, venue) or None,
            doi=_get_str_attr(paper, 'doi', '') or None,
        )

    def _parse_authors(self, authors: Any) -> List[str]:
        if not authors:
            return []
        # Handle both list and tuple (acl-anthology uses tuple)
        if isinstance(authors, (list, tuple)):
            result = []
            for a in authors:
                first = getattr(a, 'first', None) or ""
                last = getattr(a, 'last', '')
                if first:
                    result.append(f"{first} {last}".strip())
                else:
                    result.append(last)
            return result
        return []

    def _parse_pdf_url(self, paper: Any) -> str:
        pdf = getattr(paper, 'pdf', None)
        if pdf is not None:
            pdf_url = getattr(pdf, 'url', None)
            if pdf_url:
                return str(pdf_url)
        web_url = getattr(paper, 'web_url', '')
        if web_url:
            if web_url.endswith('/'):
                web_url = web_url[:-1]
            return web_url + '.pdf'
        return ""

    def download_by_doi(self, doi: str, output_dir: Optional[str] = None) -> Dict:
        """
        Download a paper from ACL Anthology by DOI.

        Args:
            doi: Digital Object Identifier (e.g., '10.18653/v1/P18-1001').
            output_dir: Directory to save the PDF.

        Returns:
            Dictionary with download information.
        """
        save_dir = Path(output_dir) if output_dir else self.download_dir
        save_dir.mkdir(parents=True, exist_ok=True)

        try:
            # ACL Anthology papers can be looked up by DOI
            paper = self.client.get(doi)
        except Exception:
            return {
                "status": "error",
                "message": f"Failed to retrieve paper by DOI '{doi}' from ACL Anthology.",
            }

        if not paper:
            return {
                "status": "error",
                "message": f"Paper with DOI '{doi}' not found in ACL Anthology.",
            }

        pdf_url = self._parse_pdf_url(paper)
        if not pdf_url:
            return {
                "status": "error",
                "message": f"No PDF URL found for paper with DOI '{doi}'.",
            }

        try:
            paper_id = str(getattr(paper, 'id', doi.replace("/", "_")))
            path, filename = self._download_file(str(pdf_url), paper_id)
            return {
                "status": "success",
                "identifier": doi,
                "path": path,
                "filename": filename,
                "title": str(getattr(paper, 'title', '')),
                "authors": self._parse_authors(getattr(paper, 'authors', [])),
                "source": "acl_anthology",
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to download PDF: {str(e)}",
            }

    def _download_file(self, url: str, identifier: str, save_dir: Optional[Path] = None) -> Tuple[str, str]:
        """
        Download a file from a URL and save it to the download directory.

        Args:
            url: URL of the file to download.
            identifier: Identifier for naming the downloaded file.
            save_dir: Directory to save the file (defaults to self.download_dir).

        Returns:
            Tuple of (file path, filename).
        """
        target_dir = save_dir if save_dir else self.download_dir
        filename = f"{identifier.replace('/', '_')}.pdf"
        path = target_dir / filename

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            with open(path, "wb") as f:
                f.write(response.content)
            return str(path), filename
        except Exception as e:
            raise RuntimeError(f"Failed to download file from {url}: {str(e)}")


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
