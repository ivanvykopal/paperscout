"""
Tests for Paper.to_bibtex() method.
"""

import pytest
from paperscout.types import Paper


class TestPaperToBibtex:
    """Tests for the to_bibtex() method and related helpers."""

    def test_to_bibtex_auto_key_generation(self):
        """Check that vaswani2017attention style key is generated."""
        paper = Paper(
            title="Attention Is All You Need",
            authors=["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
            year=2017,
            abstract="The Transformer is a new architecture...",
            source="arxiv",
            identifier="1706.03762",
            url="https://arxiv.org/abs/1706.03762",
            pdf_url=None,
            published=None,
            categories=[],
        )
        bibtex = paper.to_bibtex()
        # Check that a key in the format vaswani2017... is generated
        assert "vaswani2017" in bibtex.lower()
        assert "@article" in bibtex

    def test_to_bibtex_custom_key(self):
        """Check custom key works."""
        paper = Paper(
            title="Attention Is All You Need",
            authors=["Ashish Vaswani"],
            year=2017,
            abstract="The Transformer...",
            source="arxiv",
            identifier="1706.03762",
            url="https://arxiv.org/abs/1706.03762",
            pdf_url=None,
            published=None,
            categories=[],
        )
        bibtex = paper.to_bibtex(entry_key="my_custom_key")
        assert "my_custom_key" in bibtex

    def test_to_bibtex_entry_type_arxiv(self):
        """Arxiv source produces @article."""
        paper = Paper(
            title="A Test Paper",
            authors=["John Doe"],
            year=2020,
            abstract="Test abstract",
            source="arxiv",
            identifier="2001.00001",
            url="https://arxiv.org/abs/2001.00001",
            pdf_url=None,
            published=None,
            categories=[],
        )
        bibtex = paper.to_bibtex()
        assert "@article" in bibtex

    def test_to_bibtex_entry_type_acl(self):
        """ACL anthology source produces @inproceedings."""
        paper = Paper(
            title="A Conference Paper",
            authors=["Jane Smith"],
            year=2021,
            abstract="Test abstract",
            source="acl_anthology",
            identifier="P21-1001",
            url="https://aclanthology.org/P21-1001/",
            pdf_url=None,
            published=None,
            categories=["Findings of the Association for Computational Linguistics"],
        )
        bibtex = paper.to_bibtex()
        assert "@inproceedings" in bibtex

    def test_to_bibtex_required_fields(self):
        """Title, author, year always present."""
        paper = Paper(
            title="Test Title",
            authors=["Alice Author"],
            year=2023,
            abstract=None,
            source="arxiv",
            identifier="2301.00001",
            url="",
            pdf_url=None,
            published=None,
            categories=[],
        )
        bibtex = paper.to_bibtex()
        assert "title = {Test Title}" in bibtex
        assert "author = {Alice Author}" in bibtex
        assert "year = {2023}" in bibtex

    def test_to_bibtex_optional_fields(self):
        """URL, abstract included when available."""
        paper = Paper(
            title="Test Title",
            authors=["Bob Writer"],
            year=2022,
            abstract="This is a test abstract.",
            source="arxiv",
            identifier="2201.00001",
            url="https://example.com/paper",
            pdf_url=None,
            published=None,
            categories=[],
        )
        bibtex = paper.to_bibtex()
        assert "url = {https://example.com/paper}" in bibtex
        assert "abstract = {This is a test abstract.}" in bibtex

    def test_to_bibtex_no_author_last_name(self):
        """Handles empty authors gracefully."""
        paper = Paper(
            title="Anonymous Paper",
            authors=[],
            year=2024,
            abstract=None,
            source="arxiv",
            identifier="2401.00001",
            url="",
            pdf_url=None,
            published=None,
            categories=[],
        )
        bibtex = paper.to_bibtex()
        # Should not crash and should produce valid output
        assert "@" in bibtex
        assert "title = {Anonymous Paper}" in bibtex
