"""
BibTeX parsing and grounding.

Each entry is converted to a :class:`~paperscout.grounding.Reference` and grounded
field by field (title, authors, year, venue, DOI, arXiv ID).
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

import bibtexparser
from rich.progress import Progress

from paperscout.grounding import (
    GroundingResult,
    Grounder,
    Reference,
    extract_arxiv_id,
    extract_doi,
    strip_latex,
)

_TRUNCATION = {"others", "et al", "et al."}


def split_bibtex_authors(field: str) -> tuple[list[str], bool]:
    """Split a BibTeX author field on top-level ``and``.

    Returns (authors, truncated) where truncated is True for ``and others``.
    Braced groups such as ``{Barnes and Noble}`` are kept intact.
    """
    if not field or not field.strip():
        return [], False
    parts, depth, start, i = [], 0, 0, 0
    text = re.sub(r"\s+", " ", field.strip())
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0 and text[i:i + 5].lower() == " and ":
            parts.append(text[start:i])
            start = i + 5
            i += 5
            continue
        i += 1
    parts.append(text[start:])
    names = [strip_latex(p).strip() for p in parts if p.strip()]
    truncated = bool(names) and names[-1].lower() in _TRUNCATION
    if truncated:
        names = names[:-1]
    return names, truncated


def reference_from_entry(entry: dict) -> Reference:
    """Build a Reference from a parsed entry (uppercase field names)."""
    authors, truncated = split_bibtex_authors(entry.get("AUTHOR", ""))
    year_match = re.search(r"\d{4}", str(entry.get("YEAR", "")))
    url = entry.get("URL", "")
    journal = entry.get("JOURNAL", "")
    venue = strip_latex(entry.get("BOOKTITLE") or journal or entry.get("HOWPUBLISHED", "") or "")
    if re.match(r"^\s*\\?url", venue, re.IGNORECASE) or venue.lower().startswith("http"):
        venue = ""

    arxiv_id = ""
    eprint = entry.get("EPRINT", "")
    if eprint and (entry.get("ARCHIVEPREFIX", "").lower() == "arxiv" or re.search(r"\d{4}\.\d{4,5}", eprint)):
        arxiv_id = extract_arxiv_id("arXiv:" + re.sub(r"^arxiv:\s*", "", eprint.strip(), flags=re.IGNORECASE))
    arxiv_id = arxiv_id or extract_arxiv_id(url, journal, entry.get("NOTE", ""), entry.get("DOI", ""))

    doi = extract_doi(entry.get("DOI", "")) or extract_doi(url)
    if doi.startswith("10.48550/arxiv."):
        # arXiv DOIs are checked through the arXiv ID instead
        arxiv_id = arxiv_id or doi.split("arxiv.", 1)[1]
        doi = ""

    return Reference(
        title=strip_latex(entry.get("TITLE", "")),
        authors=authors,
        authors_truncated=truncated,
        year=int(year_match.group()) if year_match else None,
        venue=venue,
        doi=doi,
        arxiv_id=arxiv_id,
        key=entry.get("ID", ""),
    )


class BibtexVerifier:
    """Ground every entry of a .bib file against bibliographic databases."""

    def __init__(self, sources: list[str] | None = None, use_cache: bool = True, grounder: Grounder | None = None):
        self.grounder = grounder or Grounder(sources=sources, use_cache=use_cache)

    def verify_file(self, path: str, workers: int = 1) -> list[GroundingResult]:
        entries = self._parse_bibtex(path)
        if not entries:
            return []
        refs = [reference_from_entry(e) for e in entries]
        return ground_all(self.grounder, refs, "Verifying BibTeX entries", workers)

    def verify_entry(self, entry: dict) -> GroundingResult:
        return self.grounder.ground(reference_from_entry(entry))

    def _parse_bibtex(self, path: str) -> list[dict]:
        """Parse a .bib file into entry dicts with uppercase field names (plus "ID")."""
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(path, encoding="latin-1") as f:
                content = f.read()

        try:
            parser = bibtexparser.bparser.BibTexParser(common_strings=True, ignore_nonstandard_types=False)
            library = bibtexparser.loads(content, parser=parser)
        except Exception as e:
            raise ValueError(f"Failed to parse BibTeX file: {e}") from e

        entries = []
        for entry in library.entries:
            entry_dict = {key.upper(): value for key, value in entry.items()}
            entry_dict["ID"] = entry.get("ID", "")
            entries.append(entry_dict)
        return entries

    def write_annotated_bibtex(
        self,
        input_path: str,
        output_path: str,
        results: list[GroundingResult],
        enrich: bool = False,
    ) -> None:
        """Copy the .bib file, prefixing each entry with grounding comments.

        With ``enrich``, a missing ``doi``/``url`` is filled from the matched record,
        but only for entries whose verdict is ``verified`` or ``review``.
        """
        with open(input_path, encoding="utf-8") as f:
            lines = f.read().split("\n")
        by_key = {r.reference.key: r for r in results}
        header = re.compile(r"^\s*@(\w+)\s*\{\s*([^,\s]+)\s*,")

        out: list[str] = []
        for line in lines:
            m = header.match(line)
            result = by_key.get(m.group(2)) if m and m.group(1).lower() not in ("comment", "string", "preamble") else None
            if result:
                out.append(f"% paperscout: {result.verdict}")
                if result.matched:
                    p = result.matched
                    out.append(f"% paperscout record: {p.title} ({p.year}, {p.venue or 'no venue'}) [{p.source}]")
                for issue in result.issues:
                    out.append(f"% paperscout issue: {issue}")
                if enrich and result.verdict in ("verified", "review") and result.matched:
                    additions = []
                    if not result.reference.doi and result.doi:
                        additions.append(f" doi = {{{result.doi}}},")
                    fields_in_entry = _entry_fields(lines, line)
                    if "url" not in fields_in_entry and result.matched.url:
                        additions.append(f" url = {{{result.matched.url}}},")
                    if additions and "doi" in fields_in_entry:
                        additions = [a for a in additions if not a.startswith(" doi")]
                    line = line[: m.end()] + "".join(additions) + line[m.end():]
            out.append(line)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(out))


def _entry_fields(lines: list[str], header_line: str) -> set[str]:
    """Lower-case field names of the entry that starts at ``header_line``."""
    start = lines.index(header_line)
    text, depth = "", 0
    for line in lines[start:]:
        text += line + "\n"
        depth += line.count("{") - line.count("}")
        if depth <= 0 and "{" in text:
            break
    return {m.lower() for m in re.findall(r"[,\s](\w+)\s*=", text)}


def ground_all(grounder: Grounder, refs: list[Reference], label: str, workers: int = 1) -> list[GroundingResult]:
    """Ground references (optionally concurrently), preserving input order."""
    results: list[GroundingResult | None] = [None] * len(refs)
    with Progress(transient=True) as progress:
        task = progress.add_task(f"[cyan]{label}...", total=len(refs))
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {pool.submit(grounder.ground, ref): i for i, ref in enumerate(refs)}
            for fut in futures:
                results[futures[fut]] = fut.result()
                progress.advance(task)
    return [r for r in results if r is not None]
