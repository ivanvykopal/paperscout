"""
Rich table formatting for paper search results.

Formatters return Rich renderables; printing belongs in the CLI.
"""

from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def _truncate(text: str, max_length: int = 60) -> str:
    """Truncate text to a maximum length."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def _format_authors(authors: list[str], max_length: int = 30) -> str:
    """Format author list for display."""
    if not authors:
        return ""
    if len(authors) > 2:
        return _truncate(f"{authors[0]} et al.", max_length)
    return _truncate(", ".join(authors), max_length)


def _year_from_date(date_str: str) -> str:
    """Extract year from date string."""
    if date_str and len(date_str) >= 4:
        return str(date_str)[:4]
    return ""


def format_papers_table(
    papers: list[dict],
    show_abstract: bool = False,
) -> Table:
    """Build a Rich table for a list of papers.

    Args:
        papers: List of paper dictionaries to display.
        show_abstract: If True, include the abstract column.

    Returns:
        A Rich Table.
    """
    table = Table(show_header=True, header_style="bold", show_lines=False)
    table.add_column("Source", style="dim", no_wrap=True)
    table.add_column("Year", justify="right", no_wrap=True)
    table.add_column("Title", style="bold")
    table.add_column("Authors", max_width=30)
    if show_abstract:
        table.add_column("Abstract", max_width=80)

    for paper in papers:
        if not paper:
            continue

        source = paper.get("_source", paper.get("source", "")).upper()
        year = _year_from_date(str(paper.get("year") or ""))
        title = _truncate(paper.get("title", ""), 50)
        authors = _format_authors(paper.get("authors", []) or [])

        row = [source, year, title, authors]
        if show_abstract:
            abstract = _truncate(paper.get("abstract", "") or "", 70)
            row.append(abstract)
        table.add_row(*row)

    total = len(papers)
    table.caption = f"Found {total} result(s)"
    table.caption_style = "dim"

    return table


def format_paper_detail(paper: dict) -> Panel:
    """Build a detailed single-paper view as a Rich Panel.

    Args:
        paper: Paper dictionary to display.

    Returns:
        A Rich Panel.
    """
    lines = Text()

    # Title
    title = paper.get("title", "")
    lines.append(title, style="bold")
    lines.append("\n\n")

    # Source
    source = paper.get("_source", paper.get("source", "")).upper()
    lines.append(f"Source: {source}\n", style="dim")

    # Authors
    authors = paper.get("authors", []) or []
    if authors:
        lines.append("Authors: ", style="bold")
        lines.append(", ".join(authors))
        lines.append("\n")

    # Year
    year = paper.get("year")
    if year:
        lines.append("Year: ", style="bold")
        lines.append(str(year))
        lines.append("\n")

    # Identifier
    identifier = paper.get("identifier", "")
    if identifier:
        lines.append("ID: ", style="bold")
        lines.append(identifier)
        lines.append("\n")

    # URL
    url = paper.get("url", "") or paper.get("abstract_url", "")
    if url:
        lines.append("URL: ", style="bold")
        lines.append(url)
        lines.append("\n")

    # PDF URL (if available)
    pdf_url = paper.get("pdf_url", "")
    if pdf_url:
        lines.append("PDF: ", style="bold")
        lines.append(pdf_url)
        lines.append("\n")

    # Abstract (if available)
    abstract = paper.get("abstract", "")
    if abstract:
        lines.append("\n")
        lines.append("Abstract: ", style="bold")
        lines.append(abstract)

    return Panel(lines, expand=False)
