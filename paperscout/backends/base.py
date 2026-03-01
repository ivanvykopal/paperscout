"""
Base backend interface for paperscout backends.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class BaseBackend(ABC):
    """
    Abstract base class for all paperscout backends.

    Each backend must implement:
    - search: Search for papers
    - download: Download a paper
    """

    name: str = "base"
    supported_sources: List[str] = []

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the backend.

        Args:
            api_key: Optional API key for the backend service.
        """
        self.api_key = api_key

    @abstractmethod
    def search(self, query: str, limit: int = 10, **kwargs) -> List[Dict]:
        """
        Search for papers.

        Args:
            query: Search query string.
            limit: Maximum number of results to return.
            **kwargs: Backend-specific parameters.

        Returns:
            List of paper search results as dictionaries.
        """
        pass

    @abstractmethod
    def download(self, identifier: str, **kwargs) -> Dict:
        """
        Download a paper by identifier.

        Args:
            identifier: Unique paper identifier (DOI, arXiv ID, etc.).
            **kwargs: Backend-specific download options.

        Returns:
            Dictionary with download information.
        """
        pass

    def validate_source(self, source: str) -> bool:
        """
        Check if the source is supported by this backend.

        Args:
            source: Source name to check.

        Returns:
            True if supported, False otherwise.
        """
        return source in self.supported_sources
