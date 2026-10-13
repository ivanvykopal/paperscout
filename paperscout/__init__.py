"""
paperscout: A multi-purpose tool for searching, downloading, and managing academic papers.

This package provides programmatic access to academic paper databases and tools
for managing your local paper collection.
"""

from paperscout.backends.acl_anthology import ACLAnthologyBackend
from paperscout.backends.arxiv import ArxivBackend
from paperscout.backends.base import BaseBackend
from paperscout.backends.crossref import CrossrefBackend
from paperscout.backends.dblp import DblpBackend
from paperscout.backends.s2cli import SemanticScholarBackend
from paperscout.bibtex import BibtexVerifier
from paperscout.client import PaperFinderClient
from paperscout.grounding import FieldCheck, Grounder, GroundingResult, Reference
from paperscout.search import PaperSearcher
from paperscout.types import Paper

__version__ = "0.4.0"
__author__ = "Ivan Vykopal"
__author_email__ = "ivan.vykopal@gmail.com"

__all__ = [
    "ACLAnthologyBackend",
    "ArxivBackend",
    "BaseBackend",
    "BibtexVerifier",
    "CrossrefBackend",
    "DblpBackend",
    "FieldCheck",
    "Grounder",
    "GroundingResult",
    "Paper",
    "PaperFinderClient",
    "PaperSearcher",
    "Reference",
    "SemanticScholarBackend",
]
