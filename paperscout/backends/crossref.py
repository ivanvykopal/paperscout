"""
Crossref backend: bibliographic search over Crossref and DOI resolution via doi.org.

Crossref covers journals and most proceedings with registered DOIs (ACL, ACM,
IEEE, Springer, ...). DOI resolution uses doi.org content negotiation, which
works for every registration agency (Crossref, DataCite/arXiv, Zenodo, ...).
"""

from __future__ import annotations

import os
import re
import time

import requests

from paperscout.backends.base import BaseBackend
from paperscout.types import Paper

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
DOI_RESOLVER_URL = "https://doi.org/"
CSL_JSON = "application/vnd.citationstyles.csl+json"


def normalize_doi(doi: str) -> str:
    """Strip resolver prefixes / ``doi:`` and lowercase (DOIs are case-insensitive)."""
    doi = (doi or "").strip()
    doi = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
    return doi.strip().rstrip(".").lower()


def _user_agent() -> str:
    mailto = os.environ.get("PAPERSCOUT_MAILTO")
    agent = "paperscout (https://github.com/ivykopal/paperscout)"
    return f"{agent}; mailto:{mailto}" if mailto else agent


def _csl_year(item: dict) -> int | None:
    for key in ("issued", "published-print", "published-online", "published", "created"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            return int(parts[0][0])
    return None


def _first(value) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value or "")


def _csl_to_paper(item: dict, source: str = "crossref") -> Paper:
    """Convert a Crossref ``works`` item or a CSL-JSON record to a Paper."""
    authors = []
    for author in item.get("author") or []:
        given = (author.get("given") or "").strip()
        family = (author.get("family") or "").strip()
        literal = (author.get("literal") or author.get("name") or "").strip()
        name = " ".join(p for p in (given, family) if p) or literal
        if name:
            authors.append(name)

    title = re.sub(r"<[^>]+>", "", _first(item.get("title"))).strip()
    doi = normalize_doi(item.get("DOI", ""))
    venue = _first(item.get("container-title")) or item.get("publisher", "") or ""
    return Paper(
        title=title,
        authors=authors,
        year=_csl_year(item),
        abstract=re.sub(r"<[^>]+>", "", item.get("abstract") or "").strip(),
        source=source,
        identifier=doi,
        url=item.get("URL") or (f"https://doi.org/{doi}" if doi else ""),
        pdf_url=None,
        published=None,
        categories=[venue] if venue else [],
        venue=venue or None,
        doi=doi or None,
    )


class CrossrefBackend(BaseBackend):
    """Search Crossref by bibliographic string and resolve DOIs."""

    name: str = "crossref"
    supported_sources: list[str] = ["crossref"]

    def __init__(self, api_key: str | None = None, timeout: float = 30.0, max_retries: int = 4):
        super().__init__(api_key)
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_total = 0

    def _get(self, url: str, **kwargs) -> requests.Response:
        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", _user_agent())
        delay = 2.0
        response = requests.get(url, headers=headers, timeout=self.timeout, **kwargs)
        for _ in range(self.max_retries):
            if response.status_code not in (429, 500, 502, 503, 504):
                break
            time.sleep(delay)
            delay *= 2
            response = requests.get(url, headers=headers, timeout=self.timeout, **kwargs)
        return response

    def search(self, query: str, limit: int = 10, **kwargs) -> list[Paper]:
        params = {"query.bibliographic": query, "rows": limit}
        mailto = os.environ.get("PAPERSCOUT_MAILTO")
        if mailto:
            params["mailto"] = mailto
        response = self._get(CROSSREF_WORKS_URL, params=params)
        response.raise_for_status()
        message = response.json().get("message", {})
        self._last_total = message.get("total-results", 0)
        return [_csl_to_paper(item) for item in message.get("items", [])]

    def lookup(self, identifier: str) -> Paper | None:
        """Resolve a DOI. Returns None if the DOI is not registered; raises on network errors."""
        doi = normalize_doi(identifier)
        if not doi:
            return None
        response = self._get(DOI_RESOLVER_URL + doi, headers={"Accept": CSL_JSON})
        if response.status_code == 404:
            return None
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError as err:
            raise RuntimeError(f"doi.org returned non-JSON metadata for {doi}") from err
        return _csl_to_paper(data, source="doi")

    def download(self, identifier: str, **kwargs) -> dict:
        return {
            "status": "error",
            "message": "Crossref does not host PDFs; download via the publisher or another backend.",
        }
