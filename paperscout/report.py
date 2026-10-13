"""
Rendering of grounding results: Rich console table, plain-text report and JSON.
"""

from __future__ import annotations

import json
from collections import Counter

from rich.table import Table

from paperscout.grounding import VERDICTS, GroundingResult

VERDICT_LABELS = {
    "verified": "🟢 verified",
    "review": "🟡 review",
    "mismatch": "🟠 mismatch",
    "not_found": "🔴 not found",
    "unverifiable": "⚪ unverifiable",
}

VERDICT_HELP = {
    "verified": "every cited field matches a published record",
    "review": "record found; minor differences worth checking",
    "mismatch": "record found but a cited field is wrong (possible hallucinated metadata)",
    "not_found": "no source knows this title (possible hallucinated reference)",
    "unverifiable": "lookups failed or no title; nothing can be concluded",
}


def summary_line(results: list[GroundingResult]) -> str:
    counts = Counter(r.verdict for r in results)
    return " | ".join(f"{VERDICT_LABELS[v]}: {counts.get(v, 0)}" for v in VERDICTS)


def _label(r: GroundingResult) -> str:
    ref = r.reference
    return ref.key or (ref.authors[0] if ref.authors else "") or "—"


def _record(r: GroundingResult) -> str:
    paper = r.matched or r.closest
    if not paper:
        return "—"
    prefix = "" if r.matched else "closest: "
    venue = f", {paper.venue}" if paper.venue else ""
    year = f" ({paper.year}{venue})" if paper.year else (f" ({paper.venue})" if paper.venue else "")
    return f"{prefix}{paper.title}{year} [{paper.source}]"


def rich_table(results: list[GroundingResult]) -> Table:
    table = Table(show_header=True, header_style="bold", show_lines=True)
    table.add_column("Ref", style="dim", max_width=22, overflow="fold")
    table.add_column("Verdict", no_wrap=True)
    table.add_column("Cited title", max_width=40)
    table.add_column("Issues", max_width=60)
    table.add_column("Record", max_width=45)
    for r in results:
        issues = "\n".join(f"• {i}" for i in r.issues) or ""
        table.add_row(_label(r), VERDICT_LABELS[r.verdict], r.reference.title or "—", issues, _record(r))
    table.caption = summary_line(results)
    table.caption_style = "dim"
    return table


def text_report(results: list[GroundingResult]) -> str:
    lines = ["Reference Grounding Report", "=" * 60, f"Total references: {len(results)}"]
    counts = Counter(r.verdict for r in results)
    for v in VERDICTS:
        lines.append(f"  {v:<13} {counts.get(v, 0):>4}  ({VERDICT_HELP[v]})")
    lines.append("")
    order = {v: i for i, v in enumerate(("not_found", "mismatch", "unverifiable", "review", "verified"))}
    for r in sorted(results, key=lambda r: order[r.verdict]):
        ref = r.reference
        lines.append(f"[{r.verdict.upper()}] {_label(r)}")
        lines.append(f"  Cited:   {ref.title}")
        if ref.authors:
            lines.append(f"  Authors: {'; '.join(ref.authors)}{' et al.' if ref.authors_truncated else ''}")
        details = ", ".join(x for x in (str(ref.year or ""), ref.venue, ref.doi, ref.arxiv_id) if x)
        if details:
            lines.append(f"  Details: {details}")
        lines.append(f"  Record:  {_record(r)}")
        if r.matched and r.matched.url:
            lines.append(f"  URL:     {r.matched.url}")
        for issue in r.issues:
            lines.append(f"  ! {issue}")
        if r.source_errors:
            lines.append("  Source errors: " + "; ".join(f"{k}: {v}" for k, v in r.source_errors.items()))
        lines.append("")
    return "\n".join(lines)


def write_json(path: str, results: list[GroundingResult]) -> None:
    payload = {
        "summary": dict(Counter(r.verdict for r in results)),
        "results": [r.to_dict() for r in results],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
