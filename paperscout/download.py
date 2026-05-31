"""
Paper download functionality.

Handles downloading PDFs by auto-detecting the identifier type (arXiv ID,
DOI, ACL Anthology ID, DBLP key) and routing to the appropriate backend.
"""

import os
import re
from pathlib import Path
from typing import Dict, Optional, Tuple


# ── identifier detection ──────────────────────────────────────────────

# DOI pattern: 10.XXXX/XXXX...
_DOI_RE = re.compile(r"^10\.\d{4,}/.+$")

# arXiv ID patterns:
#   - "arXiv:XXXX.XXXXX" (canonical, optional version suffix)
#   - "XXXX.XXXXX" (bare ID — looks like a float but with many digits)
_ARXIV_CANONICAL_RE = re.compile(r"^arXiv:(\d{4}\.\d{4,})(v\d+)?$", re.IGNORECASE)
_ARXIV_BARE_RE = re.compile(r"^(\d{4}\.\d{4,})(v\d+)?$")

# ACL Anthology ID patterns:
#   - P18-1001, D19-1001, W18-1001, etc. (year-based proceedings)
#   - 2020.acl-main.1, 2023.emnlp-main.1, etc. (venue-based)
#   - J90-1001, Q19-1001 (older format, journals)
_ACL_RE = re.compile(
    r"^([A-Z]\d{2}-\d{4})$"                    # P18-1001 style
    r"|^(\d{4}\.[a-z]+[^/]+\d+)$"              # 2020.acl-main.1 style
    r"|^(\d{4}\.[a-z]+)$",                      # 2020.acl (shorthand)
    re.IGNORECASE,
)

# DBLP key pattern: journals/..., conf/..., books/..., phd/..., tr/...
_DBLP_RE = re.compile(
    r"^(journals|conf|books|phd|tr|series|reference)/.+",
    re.IGNORECASE,
)

# Semantic Scholar ID: 40-char hex string
_S2_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


def _detect_identifier_type(identifier: str) -> str:
    """
    Detect the type of a paper identifier.

    Returns one of: 'arxiv', 'doi', 'acl_anthology', 'dblp',
    'semantic_scholar', or 'unknown'.
    """
    stripped = identifier.strip()

    if _DOI_RE.match(stripped):
        return "doi"

    if _ARXIV_CANONICAL_RE.match(stripped) or _ARXIV_BARE_RE.match(stripped):
        return "arxiv"

    if _ACL_RE.match(stripped):
        return "acl_anthology"

    if _DBLP_RE.match(stripped):
        return "dblp"

    if _S2_RE.match(stripped):
        return "semantic_scholar"

    return "unknown"


# ── PaperDownloader ───────────────────────────────────────────────────


class PaperDownloader:
    """
    Download papers from various sources.

    Automatically detects the identifier type and routes the request
    to the correct backend. Supports arXiv IDs, DOIs, ACL Anthology IDs,
    DBLP keys, and Semantic Scholar IDs.

    Usage::

        downloader = PaperDownloader(output_dir="./papers")
        result = downloader.download("arXiv:2301.12345")
        result = downloader.download("10.18653/v1/P18-1001")
    """

    def __init__(self, output_dir: Optional[str] = None):
        """
        Initialize the paper downloader.

        Args:
            output_dir: Directory to save downloaded PDFs.
                        Defaults to ./downloads.
        """
        self.output_dir = Path(output_dir or "./downloads")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def download(
        self,
        identifier: str,
        source: Optional[str] = None,
        output_dir: Optional[str] = None,
        **kwargs,
    ) -> Dict:
        """
        Download a paper PDF by identifier.

        Args:
            identifier: Paper identifier (DOI, arXiv ID, ACL ID, DBLP key, etc.).
            source: Source backend to use. Auto-detected from the identifier
                    if not provided.
            output_dir: Override the default output directory for this download.
            **kwargs: Additional backend-specific options.

        Returns:
            Dictionary with: status, identifier, path, filename, title,
            authors, source.
        """
        # Determine the source backend
        if source is None:
            source = _detect_identifier_type(identifier)

        if source == "unknown":
            return {
                "status": "error",
                "message": (
                    f"Could not detect identifier type for '{identifier}'. "
                    "Please specify the source explicitly with --source "
                    "(arxiv, acl_anthology, dblp, semantic_scholar)."
                ),
            }

        # Resolve the download directory
        save_dir = Path(output_dir) if output_dir else self.output_dir

        if source == "doi":
            return self._download_by_doi(identifier, save_dir, **kwargs)

        # Route to the appropriate backend
        backend = self._get_backend(source)
        if backend is None:
            return {
                "status": "error",
                "message": (
                    f"Source '{source}' is not supported for downloading. "
                    "Supported sources: arxiv, acl_anthology, dblp, semantic_scholar."
                ),
            }

        # Tell the backend where to save the file
        return backend.download(identifier, output_dir=str(save_dir), **kwargs)

    def _download_by_doi(
        self, doi: str, save_dir: Path, **kwargs
    ) -> Dict:
        """
        Download a paper by DOI.

        Tries multiple backends in order to find and download the paper:
        1. arXiv (many papers have both a DOI and an arXiv version)
        2. Semantic Scholar (can resolve DOIs to papers, sometimes has PDF URLs)
        3. Direct DOI resolution via doi.org

        Args:
            doi: Digital Object Identifier.
            save_dir: Directory to save the PDF.
            **kwargs: Additional options.

        Returns:
            Dictionary with download information.
        """
        # Strategy 1: Try Semantic Scholar (has DOI lookup)
        try:
            from paperscout.backends.s2cli import SemanticScholarBackend

            s2 = SemanticScholarBackend()
            s2_result = s2.download(doi, output_dir=str(save_dir))
            if s2_result.get("status") == "success":
                return s2_result
        except ImportError:
            pass
        except Exception:
            pass

        # Strategy 2: Try ACL Anthology (has DOI-based paper access)
        try:
            from paperscout.backends.acl_anthology import ACLAnthologyBackend

            acl = ACLAnthologyBackend()
            # ACL Anthology papers can often be accessed via DOI
            acl_result = acl.download_by_doi(doi, output_dir=str(save_dir))
            if acl_result.get("status") == "success":
                return acl_result
        except ImportError:
            pass
        except Exception:
            pass

        # Strategy 3: Direct DOI resolution via doi.org API
        result = self._resolve_doi_direct(doi, save_dir)
        if result.get("status") == "success":
            return result

        return {
            "status": "error",
            "message": (
                f"Could not download paper with DOI '{doi}'. "
                "No backend was able to find a PDF for this DOI."
            ),
        }

    def _resolve_doi_direct(self, doi: str, save_dir: Path) -> Dict:
        """
        Resolve a DOI directly via doi.org API.

        Uses the doi.org content negotiation to find the paper's URL,
        then attempts to download the PDF.

        Args:
            doi: Digital Object Identifier.
            save_dir: Directory to save the PDF.

        Returns:
            Dictionary with download information.
        """
        try:
            import requests
        except ImportError:
            return {
                "status": "error",
                "message": "requests library is required for DOI resolution."
            }

        try:
            # Use doi.org content negotiation to get metadata
            headers = {"Accept": "application/vnd.citationstyles.csl+json"}
            doi_url = f"https://doi.org/{doi}"
            response = requests.get(doi_url, headers=headers, timeout=15)
            response.raise_for_status()
            metadata = response.json()

            title = metadata.get("title", doi)
            # Try to get PDF from the resolved URL or common patterns
            pdf_url = metadata.get("URL", "")

            if not pdf_url:
                return {
                    "status": "error",
                    "message": f"No URL found for DOI '{doi}'.",
                }

            # Some publishers host PDFs at url + '.pdf' or url + '/pdf'
            pdf_candidates = [pdf_url]
            if not pdf_url.endswith(".pdf"):
                pdf_candidates.extend([
                    pdf_url.rstrip("/") + ".pdf",
                    pdf_url.rstrip("/") + "/pdf",
                ])

            for candidate_url in pdf_candidates:
                try:
                    pdf_response = requests.get(
                        candidate_url, timeout=30, allow_redirects=True
                    )
                    content_type = pdf_response.headers.get("Content-Type", "")
                    if (
                        pdf_response.status_code == 200
                        and (
                            "application/pdf" in content_type
                            or candidate_url.endswith(".pdf")
                        )
                    ):
                        safe_doi = doi.replace("/", "_")
                        filename = f"{safe_doi}.pdf"
                        path = save_dir / filename

                        with open(path, "wb") as f:
                            f.write(pdf_response.content)

                        return {
                            "status": "success",
                            "identifier": doi,
                            "path": str(path),
                            "filename": filename,
                            "title": title,
                            "source": "doi",
                        }
                except Exception:
                    continue

            return {
                "status": "error",
                "message": (
                    f"Found metadata for DOI '{doi}' but could not download "
                    "the PDF. The publisher may require authentication or "
                    "the PDF may not be freely accessible."
                ),
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"DOI resolution failed for '{doi}': {str(e)}",
            }

    def _get_backend(self, source: str):
        """
        Get a backend instance for the given source.

        Args:
            source: Source name (e.g., 'arxiv', 'acl_anthology').

        Returns:
            Backend instance, or None if the source is not supported or unavailable.
        """
        from paperscout.search import PaperSearcher

        searcher = PaperSearcher()

        if source not in searcher.BACKENDS:
            return None

        try:
            return searcher._get_backend(source)
        except ImportError:
            return None
