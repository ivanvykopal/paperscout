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
        choices=["all", "arxiv", "dblp", "semantic_scholar", "acl_anthology", "crossref"],
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
    match_parser.add_argument(
        "--bibtex",
        action="store_true",
        help="Output results as BibTeX",
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
        choices=["all", "arxiv", "dblp", "semantic_scholar", "acl_anthology", "crossref"],
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
    search_parser.add_argument(
        "--bibtex",
        action="store_true",
        help="Output results as BibTeX",
    )

    # Download command
    download_parser = subparsers.add_parser(
        "download", help="Download a paper PDF"
    )
    download_parser.add_argument(
        "identifier",
        help="Paper identifier (DOI, arXiv ID, ACL ID, DBLP key, etc.). "
             "The type is auto-detected — no need to specify --source.",
    )
    download_parser.add_argument(
        "-s",
        "--source",
        choices=["arxiv", "dblp", "semantic_scholar", "acl_anthology"],
        default=None,
        help="Source backend to use (auto-detected from identifier if not specified)",
    )
    download_parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="./downloads",
        help="Directory to save the downloaded PDF (default: ./downloads)",
    )
    download_parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    # Verify commands - ground references field by field
    verify_parser = subparsers.add_parser(
        "verify",
        help="Ground BibTeX entries (title, authors, year, venue, DOI, arXiv ID)",
    )
    verify_parser.add_argument("file", help="Path to .bib file to verify")
    verify_parser.add_argument(
        "--enrich",
        action="store_true",
        help="With -o: add missing doi/url to verified/review entries",
    )
    verify_parser.add_argument(
        "-o", "--output",
        help="Write annotated .bib (verdict and issues as comments) to this path",
    )
    _add_verify_arguments(verify_parser)

    verify_md_parser = subparsers.add_parser(
        "verify-markdown",
        help="Ground references from a markdown file (References section)",
    )
    verify_md_parser.add_argument(
        "file",
        help="Path to markdown file (.md) with References section",
    )
    verify_md_parser.add_argument(
        "-o", "--output",
        help="Write plain-text report to this path (same as --report)",
    )
    _add_verify_arguments(verify_md_parser)

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
            if args.bibtex:
                output_results(best_match.to_bibtex(), args.output, as_json=False)
            else:
                output_results(best_match, args.output, args.json)
        else:
            console.print("[bold red]No matching paper found.[/bold red]")
            sys.exit(1)

    elif args.command == "search":
        results = client.search(
            args.query, source=args.source, limit=args.limit
        )
        if args.bibtex:
            # Output as BibTeX
            bibtex_output = "\n\n".join(p.to_bibtex() for p in results)
            output_results(bibtex_output, args.output, as_json=False)
        else:
            output_results(
                results, args.output, args.json,
                show_abstract=args.abstract,
                show_similarity=not args.no_similarity,
                total_found=client.last_search_total,
            )

    elif args.command == "download":
        result = client.download(
            args.identifier,
            source=args.source,
            output_dir=args.output,
        )
        # Display the result to console (no file output — --output controls
        # the PDF save directory, not where to write the status text)
        if args.json:
            console.print(json.dumps(result, indent=2))
        elif result.get("status") == "success":
            console.print(
                f"[green]✓ Downloaded: {result.get('title', args.identifier)}[/green]"
            )
            console.print(f"  Saved to: {result.get('path', 'unknown')}")
        else:
            console.print(
                f"[red]✗ Download failed: {result.get('message', 'Unknown error')}[/red]"
            )

    elif args.command in ("verify", "verify-markdown"):
        from paperscout import report

        sources = [s.strip() for s in args.sources.split(",")] if args.sources else None
        try:
            if args.command == "verify":
                from paperscout.bibtex import BibtexVerifier

                verifier = BibtexVerifier(sources=sources, use_cache=not args.no_cache)
                results = verifier.verify_file(args.file, workers=args.workers)
            else:
                from paperscout.markdown_refs import MarkdownRefParser

                md_parser = MarkdownRefParser(sources=sources, use_cache=not args.no_cache)
                results = md_parser.verify_file(args.file, workers=args.workers)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            sys.exit(2)

        if not results:
            console.print("[yellow]No references found in the input.[/yellow]")
            sys.exit(2)

        console.print(report.rich_table(results))

        text_path = args.report or (args.output if args.command == "verify-markdown" else None)
        if text_path:
            with open(text_path, "w", encoding="utf-8") as f:
                f.write(report.text_report(results))
            console.print(f"[green]Report written to {text_path}[/green]")
        if args.command == "verify" and args.output:
            verifier.write_annotated_bibtex(args.file, args.output, results, enrich=args.enrich)
            console.print(f"[green]Annotated BibTeX written to {args.output}[/green]")
        if args.json_output:
            report.write_json(args.json_output, results)
            console.print(f"[green]JSON report written to {args.json_output}[/green]")

        if any(r.verdict in ("mismatch", "not_found") for r in results):
            sys.exit(1)


def _add_verify_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-s", "--source",
        dest="sources",
        help="Sources to query, comma-separated "
             "(default: crossref,dblp,semantic_scholar,arxiv,acl_anthology)",
    )
    parser.add_argument(
        "-j", "--json",
        dest="json_output",
        help="Write JSON report (per-field checks) to this path",
    )
    parser.add_argument("--report", help="Write plain-text report to this path")
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="References verified concurrently (default: 1; raise only with an S2_API_KEY)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore the on-disk lookup cache (~/.cache/paperscout, 30-day TTL)",
    )


def output_results(
    data,
    output_file: Optional[str] = None,
    as_json: bool = False,
    show_abstract: bool = False,
    show_similarity: bool = True,
    total_found: int | None = None,
):
    """Output results to file or stdout."""
    if as_json:
        output = json.dumps(data, indent=2)
    else:
        if isinstance(data, str):
            # Direct string output (e.g., BibTeX)
            output = data
        elif isinstance(data, list):
            output = format_papers_table(
                data,
                show_abstract=show_abstract,
                show_similarity=show_similarity,
                total_found=total_found,
            )
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
