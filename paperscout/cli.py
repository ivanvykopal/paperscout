"""
Command-line interface for paperscout.
"""

import argparse
import json
import sys
from typing import Optional

from paperscout.client import PaperFinderClient
from paperscout.formatter import format_paper_detail, format_papers_table
from rich.console import Console

console = Console()


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="paperscout",
        description="A multi-purpose tool for searching, downloading, and managing academic papers.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Match command - get single best match by title
    match_parser = subparsers.add_parser(
        "match", help="Get the best matching paper by title"
    )
    match_parser.add_argument(
        "query", help="Paper title to search for"
    )
    match_parser.add_argument(
        "-s",
        "--source",
        choices=["all", "arxiv", "dblp", "semantic_scholar", "acl_anthology"],
        default="all",
        help="Source to search (default: all - searches all backends)",
    )
    match_parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output file (default: stdout)",
    )
    match_parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    # Search command
    search_parser = subparsers.add_parser(
        "search", help="Search for academic papers"
    )
    search_parser.add_argument(
        "query", help="Search query string"
    )
    search_parser.add_argument(
        "-s",
        "--source",
        choices=["all", "arxiv", "dblp", "semantic_scholar", "acl_anthology"],
        default="all",
        help="Source to search (default: all - searches all backends)",
    )
    search_parser.add_argument(
        "-l",
        "--limit",
        type=int,
        default=10,
        help="Maximum number of results (default: 10)",
    )
    search_parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output file (default: stdout)",
    )
    search_parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    search_parser.add_argument(
        "-a",
        "--abstract",
        action="store_true",
        help="Show abstract in results",
    )
    search_parser.add_argument(
        "--no-similarity",
        action="store_true",
        help="Hide similarity score in results",
    )

    # Download command
    download_parser = subparsers.add_parser(
        "download", help="Download a paper"
    )
    download_parser.add_argument(
        "identifier", help="Paper identifier (DOI, arXiv ID, etc.)"
    )
    download_parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output directory (default: ./downloads)",
    )
    download_parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    client = PaperFinderClient()

    if args.command == "match":
        results = client.search(
            args.query, source=args.source, limit=10
        )
        if results:
            best_match = results[0]
            output_results(best_match, args.output, args.json)
        else:
            console.print("[bold red]No matching paper found.[/bold red]")
            sys.exit(1)

    elif args.command == "search":
        results = client.search(
            args.query, source=args.source, limit=args.limit
        )
        output_results(results, args.output, args.json, show_abstract=args.abstract, show_similarity=not args.no_similarity)

    elif args.command == "download":
        result = client.download(args.identifier)
        output_results(result, args.output, args.json)


def output_results(
    data, output_file: Optional[str] = None, as_json: bool = False, show_abstract: bool = False, show_similarity: bool = True
):
    """Output results to file or stdout."""
    if as_json:
        output = json.dumps(data, indent=2)
    else:
        if isinstance(data, list):
            output = format_papers_table(data, show_abstract=show_abstract, show_similarity=show_similarity)
        else:
            output = format_paper_detail(data)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(str(output))
        console.print(f"[green]Results written to {output_file}[/green]")
    else:
        console.print(output)


if __name__ == "__main__":
    main()
