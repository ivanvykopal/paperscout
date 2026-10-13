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


if __name__ == '__main__':
    unittest.main()
