"""
Tests for MarkdownRefParser class.
"""

import unittest
import tempfile
import os


class TestMarkdownRefParser:
    """Test cases for MarkdownRefParser class."""

    def test_parse_valid_references(self):
        """Test parsing a valid markdown file with references."""
        from paperscout.markdown_refs import MarkdownRefParser

        parser = MarkdownRefParser()

        # Create a test markdown file
        md_content = """# Test Paper

This is a test paper with references.

## References

John Doe, Jane Smith, and Bob Johnson. 2023. Attention Is All You Need. In Proceedings of NeurIPS 2023.

Alice Brown. 2024. Deep Learning for NLP. Preprint, arXiv:2401.00001.
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(md_content)
            temp_path = f.name

        try:
            references = parser.parse_file(temp_path)
            assert len(references) == 2
            assert references[0]['title'] == "Attention Is All You Need"
            assert len(references[0]['authors']) == 3
            assert references[0]['year'] == 2023
        finally:
            os.unlink(temp_path)

    def test_parse_empty_references(self):
        """Test parsing a markdown file with no references section."""
        from paperscout.markdown_refs import MarkdownRefParser

        parser = MarkdownRefParser()

        md_content = """# Test Paper

This is a test paper with no references.
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(md_content)
            temp_path = f.name

        try:
            references = parser.parse_file(temp_path)
            assert len(references) == 0
        finally:
            os.unlink(temp_path)

    def test_parse_no_references_header(self):
        """Test parsing a markdown file without References header."""
        from paperscout.markdown_refs import MarkdownRefParser

        parser = MarkdownRefParser()

        md_content = """# Test Paper

This is a test paper.

Some citation text here.
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(md_content)
            temp_path = f.name

        try:
            references = parser.parse_file(temp_path)
            assert len(references) == 0
        finally:
            os.unlink(temp_path)

    def test_parse_single_author(self):
        """Test parsing reference with single author."""
        from paperscout.markdown_refs import MarkdownRefParser

        parser = MarkdownRefParser()

        md_content = """# Test

## References

Albert Einstein. 1905. On the Electrodynamics of Moving Bodies. Annalen der Physik.
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(md_content)
            temp_path = f.name

        try:
            references = parser.parse_file(temp_path)
            assert len(references) == 1
            assert references[0]['authors'] == ["Albert Einstein"]
            assert references[0]['year'] == 1905
        finally:
            os.unlink(temp_path)

    def test_parse_organization_author(self):
        """Test parsing reference with organization as author."""
        from paperscout.markdown_refs import MarkdownRefParser

        parser = MarkdownRefParser()

        md_content = """# Test

## References

BerriAI. 2024. LiteLLM: A unified interface for LLM apis. https://github.com/BerriAI/litellm.
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(md_content)
            temp_path = f.name

        try:
            references = parser.parse_file(temp_path)
            assert len(references) == 1
            assert "BerriAI" in references[0]['authors'][0]
            assert references[0]['year'] == 2024
        finally:
            os.unlink(temp_path)

    def test_parse_multiline_reference(self):
        """Test parsing multi-line reference."""
        from paperscout.markdown_refs import MarkdownRefParser

        parser = MarkdownRefParser()

        md_content = """# Test

## References

Martin Fajcik, Martin Docekal, Jan Dolezal, Karel Ondrej, Karel Beneš, Jan Kapsa, Pavel Smrz, Alexander Polok, Michal Hradis, Zuzana Neverilova, Ales Horak, Radoslav Sabol, Michal Stefanik, Adam Jirkovsky, David Adamczyk, Petr Hyner, Jan Hula, and Hynek Kydlicek. 2025. BenCzechMark: A Czech-Centric Multitask and Multimetric Benchmark for Large Language Models with Duel Scoring Mechanism. Transactions of the Association for Computational Linguistics, 13:1068-1095.
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(md_content)
            temp_path = f.name

        try:
            references = parser.parse_file(temp_path)
            assert len(references) == 1
            assert references[0]['year'] == 2025
            assert "BenCzechMark" in references[0]['title']
        finally:
            os.unlink(temp_path)

    def test_parse_with_and_others(self):
        """Test parsing reference with 'and X others' pattern."""
        from paperscout.markdown_refs import MarkdownRefParser

        parser = MarkdownRefParser()

        md_content = """# Test

## References

Aaron Grattafiori, Abhimanyu Dubey, Abhinav Jauhri, and 542 others. 2024. The Llama 3 Herd of Models. Preprint, arXiv:2407.21783.
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(md_content)
            temp_path = f.name

        try:
            references = parser.parse_file(temp_path)
            assert len(references) == 1
            # Should not include "542 others" in authors list
            assert "542" not in ' '.join(references[0]['authors'])
            assert references[0]['year'] == 2024
        finally:
            os.unlink(temp_path)

    def test_verify_file_returns_results(self):
        """Test verifying references from a markdown file."""
        from paperscout.markdown_refs import MarkdownRefParser

        parser = MarkdownRefParser()

        md_content = """# Test

## References

Ashish Vaswani, Noam Shazeer, and Niki Parmar. 2017. Attention Is All You Need. In Proceedings of NeurIPS 2017.
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(md_content)
            temp_path = f.name

        try:
            results = parser.verify_file(temp_path)
            assert len(results) == 1
            assert results[0].extracted_title == "Attention Is All You Need"
            assert len(results[0].extracted_authors) == 3
        finally:
            os.unlink(temp_path)

    def test_format_report_produces_output(self):
        """Test that format_report produces expected output."""
        from paperscout.markdown_refs import MarkdownRefParser, ReferenceVerificationResult

        parser = MarkdownRefParser()

        results = [
            ReferenceVerificationResult(
                citation_text="Vaswani et al. 2017. Attention Is All You Need.",
                extracted_title="Attention Is All You Need",
                extracted_authors=["Vaswani", "Shazeer"],
                extracted_year=2017,
                confidence=0.95,
                verdict="verified",
                matched_paper=None,
                backend_used="arxiv",
                discrepancies=[],
            ),
            ReferenceVerificationResult(
                citation_text="Fake Author. 2099. Nonexistent Paper.",
                extracted_title="Nonexistent Paper",
                extracted_authors=["Fake Author"],
                extracted_year=2099,
                confidence=0.1,
                verdict="suspicious",
                matched_paper=None,
                backend_used=None,
                discrepancies=["not found"],
                error="not found in any backend",
            ),
        ]

        report = parser.format_report(results)

        assert "Markdown References Verification Report" in report
        assert "Total references: 2" in report
        assert "Verified: 1" in report
        assert "Suspicious: 1" in report
        assert "Attention Is All You Need" in report

    def test_find_references_section(self):
        """Test finding References section in markdown content."""
        from paperscout.markdown_refs import MarkdownRefParser

        parser = MarkdownRefParser()

        content = """# Paper Title

Abstract here.

## Introduction

Some text.

## References

Author. 2024. Title. Venue.

## Appendix

More text.
"""

        refs = parser._find_references_section(content)
        assert refs is not None
        assert "Author. 2024. Title." in refs
        assert "Appendix" not in refs

    def test_split_reference_entries(self):
        """Test splitting references into individual entries."""
        from paperscout.markdown_refs import MarkdownRefParser

        parser = MarkdownRefParser()

        content = """Author1. 2023. Title1. Venue1.

Author2. 2024. Title2. Venue2.

Author3. 2025. Title3. Venue3.
"""

        entries = parser._split_reference_entries(content)
        assert len(entries) == 3
        assert "Title1" in entries[0]
        assert "Title2" in entries[1]
        assert "Title3" in entries[2]

    def test_parse_authors_field(self):
        """Test parsing author field."""
        from paperscout.markdown_refs import MarkdownRefParser

        parser = MarkdownRefParser()

        # Test various author formats
        authors = parser._parse_authors("John Doe, Jane Smith, and Bob Johnson")
        assert len(authors) == 3
        assert "John Doe" in authors
        assert "Jane Smith" in authors
        assert "Bob Johnson" in authors

        # Test with "and X others"
        authors = parser._parse_authors("Alice Brown, and 20 others.")
        assert len(authors) == 1
        assert "20" not in authors[0]

    def test_compute_confidence(self):
        """Test confidence computation."""
        from paperscout.markdown_refs import MarkdownRefParser
        from paperscout.types import Paper

        parser = MarkdownRefParser()

        reference = {
            'title': 'Attention Is All You Need',
            'authors': ['Vaswani', 'Shazeer'],
            'year': 2017,
            'raw_text': 'Vaswani et al. 2017. Attention Is All You Need.'
        }

        paper = Paper(
            title="Attention Is All You Need",
            authors=["Ashish Vaswani", "Noam Shazeer"],
            year=2017,
            abstract="Test abstract",
            source="arxiv",
            identifier="1706.03762",
            url="https://arxiv.org/abs/1706.03762",
            pdf_url=None,
            published=None,
            categories=[],
        )

        score, discrepancies = parser._compute_confidence(reference, paper)
        assert score >= 0.7  # High confidence for title+year exact match with last-name-only authors


class TestMarkdownRefIntegration(unittest.TestCase):
    """Integration tests for markdown reference verification."""

    def test_full_verification_workflow(self):
        """Test full verification workflow with real markdown file."""
        from paperscout.markdown_refs import MarkdownRefParser

        # Use the actual Slovak_LLM_Benchmark markdown file if it exists
        test_file = "/mnt/c/Users/ivan.vykopal/Desktop/Ivan/Projects/paper-finder/Slovak_LLM_Benchmark___EMNLP_2026.md"

        if os.path.exists(test_file):
            parser = MarkdownRefParser()
            references = parser.parse_file(test_file)

            # Should find many references
            self.assertGreater(len(references), 10)

            # Verify some references were parsed correctly
            verified_refs = [r for r in references if r.get('title') and r.get('year')]
            self.assertGreater(len(verified_refs), 5)

    def test_verify_with_specific_source(self):
        """Test verifying references with specific source."""
        from paperscout.markdown_refs import MarkdownRefParser

        parser = MarkdownRefParser()

        md_content = """# Test

## References

Alex Wang, Amanpreet Singh, Julian Michael, Felix Hill, Omer Levy, and Samuel R. Bowman. 2019b. GLUE: A multi-task benchmark and analysis platform for natural language understanding. In 7th International Conference on Learning Representations, ICLR 2019, New Orleans, LA, USA, May 6-9, 2019. OpenReview.net.
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(md_content)
            temp_path = f.name

        try:
            results = parser.verify_file(temp_path, sources=["arxiv"])
            assert len(results) == 1
            # Should at least attempt to search
            self.assertIsNotNone(results[0])
        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()
