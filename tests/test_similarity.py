"""Tests for the similarity module."""

import unittest

from paperscout.similarity import _title_similarity, _normalize_title


class TestNormalizeTitle(unittest.TestCase):
    """Test cases for title normalization."""

    def test_basic_normalization(self):
        """Test basic title normalization."""
        self.assertEqual(_normalize_title("Hello World"), "hello world")

    def test_lower_case_conversion(self):
        """Test lowercase conversion."""
        self.assertEqual(_normalize_title("HELLO WORLD"), "hello world")

    def test_extra_whitespace(self):
        """Test extra whitespace handling."""
        self.assertEqual(_normalize_title("  Hello   World  "), "hello world")

    def test_punctuation_removal(self):
        """Test punctuation removal."""
        self.assertEqual(_normalize_title("Hello, World!"), "hello world")
        self.assertEqual(_normalize_title("Title: 'Test'"), "title test")

    def test_empty_string(self):
        """Test empty string."""
        self.assertEqual(_normalize_title(""), "")

    def test_none_string(self):
        """Test None input."""
        self.assertEqual(_normalize_title(None), "")


class TestTitleSimilarity(unittest.TestCase):
    """Test cases for title similarity."""

    def test_exact_match(self):
        """Test exact match returns 1.0."""
        score = _title_similarity("Attention Is All You Need", "Attention Is All You Need")
        self.assertEqual(score, 1.0)

    def test_different_titles_no_match(self):
        """Test completely different titles."""
        score = _title_similarity("Machine Learning", "Cooking Recipes")
        self.assertEqual(score, 0.0)

    def test_partial_overlap(self):
        """Test partial title overlap."""
        score = _title_similarity("Attention Is All You Need", "Attention Is All")
        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)

    def test_case_insensitive(self):
        """Test case insensitive matching."""
        score = _title_similarity("ATTENTION IS ALL", "attention is all")
        self.assertEqual(score, 1.0)

    def test_punctuation_insensitive(self):
        """Test punctuation insensitive matching."""
        score = _title_similarity("Hello, World!", "hello world")
        self.assertEqual(score, 1.0)

    def test_empty_strings(self):
        """Test empty strings."""
        self.assertEqual(_title_similarity("", ""), 0.0)
        self.assertEqual(_title_similarity("Hello", ""), 0.0)
        self.assertEqual(_title_similarity("", "World"), 0.0)

    def test_single_word_match(self):
        """Test single word match."""
        self.assertEqual(_title_similarity("test", "test"), 1.0)

    def test_single_word_no_match(self):
        """Test single word no match."""
        self.assertEqual(_title_similarity("test", "other"), 0.0)


if __name__ == "__main__":
    unittest.main()
