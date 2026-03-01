"""Tests for the backend architecture."""

import unittest
from unittest.mock import patch

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
        with patch("paper_finder.backends.arxiv.ARXIVY_AVAILABLE", True):
            with patch("paper_finder.backends.arxiv.ArxivBackend.__init__", return_value=None):
                from paper_finder.backends.arxiv import ArxivBackend
                backend = ArxivBackend()
                backend.client = None  # Mock client
                self.assertIsInstance(backend, BaseBackend)

    def test_arxiv_backend_search_method_exists(self):
        """Test that ArxivBackend has a search method."""
        with patch("paper_finder.backends.arxiv.ARXIVY_AVAILABLE", True):
            with patch("paper_finder.backends.arxiv.ArxivBackend.__init__", return_value=None):
                from paper_finder.backends.arxiv import ArxivBackend
                backend = ArxivBackend()
                self.assertTrue(hasattr(backend, 'search'))
                self.assertTrue(callable(getattr(backend, 'search')))


class TestDblpBackend(unittest.TestCase):
    """Test cases for DblpBackend."""

    def test_dblp_backend_inherits_base(self):
        """Test that DblpBackend inherits from BaseBackend."""
        with patch("paper_finder.backends.dblp.DBLPCLI_AVAILABLE", True):
            with patch("paper_finder.backends.dblp.DblpBackend.__init__", return_value=None):
                from paper_finder.backends.dblp import DblpBackend
                backend = DblpBackend()
                backend.client = None  # Mock client
                self.assertIsInstance(backend, BaseBackend)

    def test_dblp_backend_search_method_exists(self):
        """Test that DblpBackend has a search method."""
        with patch("paper_finder.backends.dblp.DBLPCLI_AVAILABLE", True):
            with patch("paper_finder.backends.dblp.DblpBackend.__init__", return_value=None):
                from paper_finder.backends.dblp import DblpBackend
                backend = DblpBackend()
                self.assertTrue(hasattr(backend, 'search'))
                self.assertTrue(callable(getattr(backend, 'search')))


class TestSemanticScholarBackend(unittest.TestCase):
    """Test cases for SemanticScholarBackend."""

    def test_s2_backend_inherits_base(self):
        """Test that SemanticScholarBackend inherits from BaseBackend."""
        with patch("paper_finder.backends.s2cli.S2CLI_AVAILABLE", True):
            with patch("paper_finder.backends.s2cli.SemanticScholarBackend.__init__", return_value=None):
                from paper_finder.backends.s2cli import SemanticScholarBackend
                backend = SemanticScholarBackend()
                backend.client = None  # Mock client
                self.assertIsInstance(backend, BaseBackend)

    def test_s2_backend_search_method_exists(self):
        """Test that SemanticScholarBackend has a search method."""
        with patch("paper_finder.backends.s2cli.S2CLI_AVAILABLE", True):
            with patch("paper_finder.backends.s2cli.SemanticScholarBackend.__init__", return_value=None):
                from paper_finder.backends.s2cli import SemanticScholarBackend
                backend = SemanticScholarBackend()
                self.assertTrue(hasattr(backend, 'search'))
                self.assertTrue(callable(getattr(backend, 'search')))


class TestACLAnthologyBackend(unittest.TestCase):
    """Test cases for ACLAnthologyBackend."""

    def test_acl_backend_inherits_base(self):
        """Test that ACLAnthologyBackend inherits from BaseBackend."""
        with patch("paper_finder.backends.acl_anthology.ACL_ANTHOLOGY_AVAILABLE", True):
            with patch("paper_finder.backends.acl_anthology.ACLAnthologyBackend.__init__", return_value=None):
                from paper_finder.backends.acl_anthology import ACLAnthologyBackend
                backend = ACLAnthologyBackend()
                backend.client = None  # Mock client
                self.assertIsInstance(backend, BaseBackend)

    def test_acl_backend_search_method_exists(self):
        """Test that ACLAnthologyBackend has a search method."""
        with patch("paper_finder.backends.acl_anthology.ACL_ANTHOLOGY_AVAILABLE", True):
            with patch("paper_finder.backends.acl_anthology.ACLAnthologyBackend.__init__", return_value=None):
                from paper_finder.backends.acl_anthology import ACLAnthologyBackend
                backend = ACLAnthologyBackend()
                self.assertTrue(hasattr(backend, 'search'))
                self.assertTrue(callable(getattr(backend, 'search')))


if __name__ == "__main__":
    unittest.main()
