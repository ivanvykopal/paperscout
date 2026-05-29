"""
Tests for Paper.to_bibtex() method and BibtexVerifier class.
"""

import unittest
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

    def test_to_bibtex_custom_entry_type(self):
        """Custom entry_type parameter overrides auto-detection."""
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
        # Arxiv normally produces @article, but we force @inproceedings
        bibtex = paper.to_bibtex(entry_type="inproceedings")
        assert "@inproceedings" in bibtex
        assert "@article" not in bibtex

    def test_to_bibtex_acl_booktitle_field(self):
        """ACL anthology papers include booktitle field from categories."""
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
            categories=["Proceedings of ACL 2021"],
        )
        bibtex = paper.to_bibtex()
        assert "@inproceedings" in bibtex
        assert "booktitle = {Proceedings of ACL 2021}" in bibtex


class TestBibtexVerifier(unittest.TestCase):
    """Test cases for BibtexVerifier class."""

    def test_verifier_initialization(self):
        """Test BibtexVerifier can be instantiated."""
        from paperscout.bibtex import BibtexVerifier
        verifier = BibtexVerifier()
        self.assertIsNotNone(verifier)

    def test_verify_empty_file(self):
        """Test verifying an empty .bib file returns empty results."""
        from paperscout.bibtex import BibtexVerifier
        import tempfile
        import os

        verifier = BibtexVerifier()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.bib', delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            results = verifier.verify_file(temp_path)
            self.assertEqual(len(results), 0)
        finally:
            os.unlink(temp_path)

    def test_format_report(self):
        """Test format_report produces expected output."""
        from paperscout.bibtex import BibtexVerifier, VerificationResult
        from paperscout.types import Paper

        verifier = BibtexVerifier()

        # Create mock verification results
        results = [
            VerificationResult(
                bib_key="vaswani2017attention",
                original_title="Attention Is All You Need",
                confidence=0.95,
                verdict="verified",
                matched_paper=Paper(
                    title="Attention Is All You Need",
                    authors=["Ashish Vaswani"],
                    year=2017,
                    abstract="Test abstract",
                    source="arxiv",
                    identifier="1706.03762",
                    url="https://arxiv.org/abs/1706.03762",
                    pdf_url=None,
                    published=None,
                    categories=[],
                ),
                backend_used="arxiv",
                discrepancies=[],
            ),
            VerificationResult(
                bib_key="unknown2020paper",
                original_title="Some Unknown Paper",
                confidence=0.40,
                verdict="suspicious",
                matched_paper=None,
                backend_used=None,
                discrepancies=["No matching paper found"],
            ),
        ]

        report = verifier.format_report(results)

        # Check key elements are present
        self.assertIn("BibTeX Verification Report", report)
        self.assertIn("Total entries: 2", report)
        self.assertIn("Verified: 1", report)
        self.assertIn("Uncertain: 0", report)
        self.assertIn("Suspicious: 1", report)
        self.assertIn("vaswani2017attention", report)
        self.assertIn("unknown2020paper", report)
        self.assertIn("0.95", report)
        self.assertIn("0.40", report)

    def test_export_as_table(self):
        """Test export_as_table returns a Rich Table."""
        from paperscout.bibtex import BibtexVerifier, VerificationResult
        from paperscout.types import Paper
        from rich.table import Table

        verifier = BibtexVerifier()

        results = [
            VerificationResult(
                bib_key="test2020key",
                original_title="Test Paper Title",
                confidence=0.75,
                verdict="uncertain",
                matched_paper=Paper(
                    title="Test Paper Title",
                    authors=["Test Author"],
                    year=2020,
                    abstract="Test",
                    source="arxiv",
                    identifier="2001.00001",
                    url="https://arxiv.org/abs/2001.00001",
                    pdf_url=None,
                    published=None,
                    categories=[],
                ),
                backend_used="arxiv",
                discrepancies=[],
            ),
        ]

        table = verifier.export_as_table(results)

        # Verify it's a Rich Table
        self.assertIsInstance(table, Table)
        # Check title
        self.assertEqual(table.title, "BibTeX Verification Results")
        # Check columns exist
        self.assertEqual(len(table.columns), 5)
