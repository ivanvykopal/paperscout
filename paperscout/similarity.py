"""
Title similarity functions for paper matching.
"""

import re


def _normalize_title(title: str) -> str:
    """
    Normalize a title for comparison by removing extra whitespace,
    punctuation, and converting to lowercase.

    Args:
        title: Original title string.

    Returns:
        Normalized title string.
    """
    if not title:
        return ""
    # Remove punctuation and convert to lowercase
    normalized = re.sub(r'[^\w\s]', '', title.lower())
    # Normalize whitespace
    normalized = ' '.join(normalized.split())
    return normalized


def _title_similarity(title1: str, title2: str) -> float:
    """
    Calculate similarity between two titles using token-based matching.

    Args:
        title1: First title.
        title2: Second title.

    Returns:
        Similarity score between 0 and 1.
    """
    norm1 = _normalize_title(title1)
    norm2 = _normalize_title(title2)

    if not norm1 or not norm2:
        return 0.0

    # Exact match
    if norm1 == norm2:
        return 1.0

    # Token-based Jaccard similarity
    tokens1 = set(norm1.split())
    tokens2 = set(norm2.split())

    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)

    if union == 0:
        return 0.0

    return intersection / union
