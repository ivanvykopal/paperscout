# paperscout — Usage Guide

`paperscout` is a multi-purpose tool for **searching, downloading, and
verifying** academic papers across multiple sources (arXiv, DBLP, Semantic
Scholar, and the ACL Anthology) through a single, consistent interface.

It ships with:

- a **CLI** (`paperscout`) for quick interactive use, and
- a **Python API** (`PaperFinderClient`, backends, and a `Paper` data model)
  for embedding into scripts and notebooks.

This guide describes how to install and use both, with runnable examples.

---

## Table of contents

1. [Installation](#1-installation)
2. [Quick start](#2-quick-start)
3. [CLI reference](#3-cli-reference)
   - [search](#search)
   - [match](#match)
   - [download](#download)
   - [verify](#verify-bibtex-files)
   - [verify-markdown](#verify-markdown-references)
4. [Python API](#4-python-api)
   - [The `PaperFinderClient`](#the-paperfinderclient)
   - [Searching](#searching)
   - [Downloading](#downloading)
5. [Using backends directly](#5-using-backends-directly)
   - [ACL Anthology (HTTP-first)](#acl-anthology-http-first)
6. [The `Paper` model](#6-the-paper-model)
7. [BibTeX export & verification](#7-bibtex-export--verification)
8. [Identifier auto-detection](#8-identifier-auto-detection)
9. [Configuration](#9-configuration)
10. [Writing a custom backend](#10-writing-a-custom-backend)

---

## 1. Installation

```bash
pip install paperscout
```

The core package (`requests`, `beautifulsoup4`, `rich`, `bibtexparser`) is
installed automatically. Each search source is an **optional extra** so you
only pull in the dependencies you actually use:

```bash
pip install paperscout[arxiv]                 # arXiv
pip install paperscout[dblp]                  # DBLP
pip install paperscout[semantic_scholar]      # Semantic Scholar
pip install paperscout[acl_anthology]         # ACL Anthology (local fallback)
pip install paperscout[all]                   # everything
```

> **Note on the ACL Anthology backend:** it talks to a hosted HTTP search API
> by default, so it works out of the box **without** the `acl_anthology` extra.
> That extra only installs the local `acl-anthology` package used as an offline
> fallback when the HTTP API is unreachable. See
> [ACL Anthology (HTTP-first)](#acl-anthology-http-first).

---

## 2. Quick start

Search across every configured source (ACL Anthology results are prioritised):

```bash
paperscout search "Attention Is All You Need"
```

Download a PDF — the identifier type is auto-detected, so no `--source` needed:

```bash
paperscout download P18-1001          # ACL Anthology ID
paperscout download arXiv:2301.12345  # arXiv ID
```

The same thing from Python:

```python
from paperscout import PaperFinderClient

client = PaperFinderClient()

for paper in client.search("Attention Is All You Need", source="all", limit=5):
    print(paper.title, "—", paper.year)

client.download("P18-1001", output_dir="./papers")
```

---

## 3. CLI reference

After installation the `paperscout` command is available. Run `paperscout` with
no arguments to see help.

### `search`

Search for papers and print a formatted table.

```bash
paperscout search "neural machine translation"

# restrict to one source
paperscout search "transformer" --source arxiv

# more results, include abstracts
paperscout search "retrieval-augmented generation" --limit 20 --abstract

# machine-readable output
paperscout search "query" --json
paperscout search "query" --output results.json

# export citations directly
paperscout search "Attention Is All You Need" --bibtex --output citations.bib
```

| Flag | Description |
|------|-------------|
| `query` (positional) | Search query (typically a paper title). |
| `-s, --source` | `all` (default), `arxiv`, `dblp`, `semantic_scholar`, `acl_anthology`. |
| `-l, --limit` | Max results (default `10`). |
| `-a, --abstract` | Show the abstract in the output. |
| `--no-similarity` | Hide the relevance score column. |
| `--bibtex` | Output results as BibTeX instead of a table. |
| `-j, --json` | Output as JSON. |
| `-o, --output` | Write to a file instead of stdout. |

### `match`

Return the **single best-matching** paper for a title.

```bash
paperscout match "Attention Is All You Need"
paperscout match "BERT" --source semantic_scholar
paperscout match "Attention Is All You Need" --bibtex --output best.bib
```

### `download`

Download a paper's PDF. Identifiers are auto-detected (see
[§8](#8-identifier-auto-detection)).

```bash
# auto-detected source
paperscout download P18-1001                 # ACL Anthology ID
paperscout download 10.18653/v1/P18-1001    # DOI
paperscout download arXiv:2301.12345         # arXiv (canonical)
paperscout download 2301.12345               # arXiv (bare)

# save somewhere specific
paperscout download arXiv:2301.12345 --output ./papers

# force a source if auto-detection is ambiguous
paperscout download P18-1001 --source acl_anthology

# JSON status for scripting
paperscout download P18-1001 --json
```

| Flag | Description |
|------|-------------|
| `identifier` (positional) | DOI, arXiv ID, ACL ID, DBLP key, or S2 ID. |
| `-s, --source` | Override auto-detection (`arxiv`, `dblp`, `semantic_scholar`, `acl_anthology`). |
| `-o, --output` | Directory to save the PDF (default `./downloads`). |
| `-j, --json` | Print the result as JSON. |

### `verify` (BibTeX files)

Ground every entry of a `.bib` file field by field (title, authors, year, venue,
DOI, arXiv ID) against Crossref, DBLP, Semantic Scholar, arXiv and the ACL Anthology.

```bash
paperscout verify references.bib
paperscout verify references.bib --source crossref,semantic_scholar,arxiv
paperscout verify references.bib -o annotated.bib --enrich --json report.json --report report.txt
```

| Flag | Description |
|------|-------------|
| `file` (positional) | Path to the `.bib` file. |
| `-s, --source` | Comma-separated sources (default: `crossref,dblp,semantic_scholar,arxiv,acl_anthology`). |
| `-o, --output` | Write an annotated `.bib` (verdict, matched record and issues as `%` comments). |
| `--enrich` | With `-o`: add missing `doi`/`url` to `verified`/`review` entries only. |
| `-j, --json` | Write a JSON report with per-field checks. |
| `--report` | Write a plain-text report, worst verdicts first. |
| `--workers` | References verified concurrently (default `1`). |
| `--no-cache` | Ignore the 30-day lookup cache. |

Verdicts: **`verified`** (all cited fields match), **`review`** (minor differences),
**`mismatch`** (a field is wrong), **`not_found`** (no source knows the title),
**`unverifiable`** (a source failed or no title). Exit code `1` if any reference is
`mismatch` or `not_found`.

### `verify-markdown` (Markdown references)

Same grounding for references listed in a `## References` section of a Markdown
file (ACL-style `Author, A. 2024. Title. Venue.` citations). Takes the same flags
except `--enrich`; `-o` writes the plain-text report.

```bash
paperscout verify-markdown paper.md --report report.txt --json report.json
```

---

## 4. Python API

### The `PaperFinderClient`

`PaperFinderClient` is the high-level entry point. It lazily creates a searcher
and downloader on first use.

```python
from paperscout import PaperFinderClient

client = PaperFinderClient()
```

### Searching

`search()` returns a list of `Paper` objects (not dicts — use attribute access).

```python
results = client.search(
    "neural machine translation",
    source="all",   # or "arxiv", "dblp", "semantic_scholar", "acl_anthology"
    limit=10,
)

for paper in results:
    print(f"[{paper.source}] {paper.title} ({paper.year}) — sim={paper.similarity}")
```

> The client's `search()` default `source` is `"arxiv"`. Pass `source="all"`
> explicitly to fan out across every configured backend (the CLI does this by
> default). When searching `all`, ACL Anthology matches are sorted to the top.

Query shortcuts are expanded automatically (e.g. `llm` →
`large language model`, `rag` → `retrieval-augmented generation`), so common
acronyms match their spelled-out forms too.

### Downloading

```python
result = client.download("P18-1001", output_dir="./papers")

if result["status"] == "success":
    print("Saved to:", result["path"])
    print("Title:", result["title"])
else:
    print("Failed:", result["message"])
```

The source is auto-detected from the identifier; pass `source=` to override.
For DOIs the downloader tries Semantic Scholar, then ACL Anthology, then a
direct `doi.org` resolution.

---

## 5. Using backends directly

Each source is a standalone backend implementing `BaseBackend`. Use them
directly when you want source-specific control without the client's merging
logic.

```python
from paperscout.backends.acl_anthology import ACLAnthologyBackend
from paperscout.backends.arxiv import ArxivBackend

acl = ACLAnthologyBackend()
for paper in acl.search("attention mechanism", limit=5):
    print(paper.title, paper.similarity)

arxiv = ArxivBackend()
for paper in arxiv.search("quantum computing", limit=5):
    print(paper.title)
```

### ACL Anthology (HTTP-first)

The ACL Anthology backend was migrated to an **HTTP-first API**. The public
`ACLAnthologyBackend` facade queries a hosted search service and falls back to
the local `acl-anthology` package only if the HTTP API fails **and** the
optional package is installed.

The service indexes the full ACL Anthology corpus (~128k papers) and exposes:

- **keyword search** — BM25 over titles + abstracts (SQLite FTS5),
- **similarity search** — cosine similarity over precomputed embeddings (FAISS),
- **paper lookup** — fetch a single paper by id.

You can use the low-level HTTP client directly for fine-grained access:

```python
from paperscout.backends.acl_anthology import _ACLAnthologyHTTPClient

client = _ACLAnthologyHTTPClient()

# health / readiness
print(client.health())
# {'status': 'ok', 'index_size': 128618, 'last_synced_at': '...'}

# semantic similarity search (results carry a `similarity` score)
for paper in client.search_similarity("attention mechanism for transformers", k=5):
    print(round(paper.similarity, 3), paper.title)

# lexical keyword search (no similarity score; BM25-ranked)
for paper in client.search_keyword("transformer attention", limit=5):
    print(paper.title)

# single paper lookup
paper = client.get_paper("N18-3011")   # returns None if not found
if paper:
    print(paper.title, paper.pdf_url)
```

The facade's `search()` merges similarity + keyword results, deduplicates by
identifier, and returns the top `limit` sorted by similarity.

```python
from paperscout.backends.acl_anthology import ACLAnthologyBackend

backend = ACLAnthologyBackend(
    base_url="https://ivykopal-acl-api.hf.space",  # optional; see Configuration
    timeout=30.0,
    max_retry_wait=30.0,
)

results = backend.search("semantic parsing", limit=10)
result = backend.download("N18-3011", output_dir="./papers")
```

The HTTP client automatically retries `503` responses (the service returns
`503` while its snapshot is still loading on cold start) with exponential
backoff, up to `max_retry_wait` seconds.

See [`docs/acl-anthology-api-reference.md`](acl-anthology-api-reference.md) for
the full HTTP API contract (endpoints, status codes, FTS5 query syntax).

---

## 6. The `Paper` model

All backends return `Paper` dataclass instances with a consistent shape:

| Field | Type | Description |
|-------|------|-------------|
| `title` | `str` | Paper title. |
| `authors` | `list[str]` | Author names. |
| `year` | `int \| None` | Publication year. |
| `abstract` | `str \| None` | Abstract text. |
| `source` | `str` | Origin (`arxiv`, `dblp`, `semantic_scholar`, `acl_anthology`). |
| `identifier` | `str` | Source-specific id (arXiv ID, DOI, ACL id, …). |
| `url` | `str` | Abstract/landing page URL. |
| `pdf_url` | `str \| None` | Direct PDF URL. |
| `published` | `str \| None` | Publication date string. |
| `categories` | `list[str]` | Venue/tags. |
| `similarity` | `float \| None` | Relevance score from search. |

```python
from paperscout import Paper

# round-trip through dict / JSON
d = paper.to_dict()
paper2 = Paper.from_dict(d)

# serialize
print(paper.to_dict())          # plain dict
print(paper.to_bibtex())        # BibTeX entry (see §7)
```

---

## 7. BibTeX export & verification

Every `Paper` can export a BibTeX entry. The entry type is inferred from the
source (`inproceedings` for ACL/DBLP, `article` for arXiv by default) and the
citation key is generated from the first author, year, and a title word.

```python
print(paper.to_bibtex())
# @inproceedings{vaswani2017attention,
#     title = {Attention Is All You Need},
#     author = {Ashish Vaswani and Noam Shazeer},
#     year = {2017},
#     url = {...},
#     booktitle = {ACL}
# }

# custom key / type
print(paper.to_bibtex(entry_key="vaswani2017", entry_type="inproceedings"))
```

### Programmatic verification

```python
from paperscout import PaperFinderClient

client = PaperFinderClient()
results = client.verify_bibtex("references.bib", sources=None, workers=1, use_cache=True)

for r in results:
    print(r.reference.key, r.verdict)
    for issue in r.issues:
        print("  !", issue)
    if r.matched:
        print("  record:", r.matched.title, r.matched.venue, r.matched.year)
```

Each `GroundingResult` exposes:

| Field | Type | Description |
|-------|------|-------------|
| `reference` | `Reference` | The cited title, authors, year, venue, DOI, arXiv ID, key, raw text. |
| `verdict` | `str` | `verified`, `review`, `mismatch`, `not_found`, or `unverifiable`. |
| `checks` | `list[FieldCheck]` | Per-field `status` (`match`, `minor`, `unconfirmed`, `mismatch`, `error`, `unchecked`), cited/found values and a note. |
| `issues` | `list[str]` | Human-readable problems, most severe first. |
| `matched` | `Paper \| None` | Primary matching record. |
| `versions` | `list[Paper]` | All records of the same work (e.g. arXiv + proceedings). |
| `closest` | `Paper \| None` | Nearest candidate when nothing matched. |
| `source_errors` | `dict[str, str]` | Sources that failed for this reference. |

Single references can be grounded directly:

```python
from paperscout import Grounder, Reference

result = Grounder().ground(Reference(
    title="Attention Is All You Need",
    authors=["Ashish Vaswani", "Noam Shazeer"], authors_truncated=True,
    year=2017, venue="NeurIPS",
))
```

Markdown files: `client.verify_markdown_references("paper.md")` returns the same
`GroundingResult` objects (`reference.raw` holds the original citation text).

---

## 8. Identifier auto-detection

When downloading, `paperscout` inspects the identifier and routes to the right
backend automatically:

| Identifier example | Detected as |
|--------------------|-------------|
| `arXiv:2301.12345`, `2301.12345`, `2301.12345v2` | `arxiv` |
| `10.18653/v1/P18-1001` | `doi` |
| `P18-1001`, `2023.acl-long.1`, `2020.acl` | `acl_anthology` |
| `journals/cacm/Smith23`, `conf/acl/Vyas23` | `dblp` |
| 40-char hex string | `semantic_scholar` |

If detection fails, pass `--source` (CLI) or `source=` (API) explicitly.

---

## 9. Configuration

### ACL Anthology API base URL

The HTTP-first ACL Anthology backend resolves its base URL in this priority
order:

1. the `base_url=` constructor argument,
2. the `PAPERSCOUT_ACL_API_URL` environment variable,
3. the built-in default (`https://ivykopal-acl-api.hf.space`).

Point at a local dev server, for example:

```bash
export PAPERSCOUT_ACL_API_URL=http://localhost:8000
paperscout search "attention" --source acl_anthology
```

```python
from paperscout.backends.acl_anthology import ACLAnthologyBackend
backend = ACLAnthologyBackend(base_url="http://localhost:8000")
```

---

## 10. Writing a custom backend

A backend is any class implementing `BaseBackend`. Register it in
`PaperSearcher.BACKENDS` to make it available to the client and CLI.

```python
from paperscout.backends.base import BaseBackend
from paperscout.types import Paper

class PubMedBackend(BaseBackend):
    name = "pubmed"
    supported_sources = ["pubmed"]

    def search(self, query: str, limit: int = 10) -> list[Paper]:
        # ...query your source...
        return [Paper(
            title="...",
            authors=["..."],
            year=2024,
            abstract="...",
            source="pubmed",
            identifier="...",
            url="...",
            pdf_url="...",
            published="",
            categories=[],
            similarity=None,
        )]

    def download(self, identifier: str, **kwargs) -> dict:
        # ...fetch and save the PDF...
        return {"status": "success", "identifier": identifier, "path": "..."}
```

Then register it:

```python
from paperscout.search import PaperSearcher

PaperSearcher.BACKENDS["pubmed"] = PubMedBackend
```

Now `client.search("query", source="pubmed")` and the CLI
(`--source pubmed`) will use it.

---

## Sources at a glance

| `source` value | Backend | Covers |
|----------------|---------|--------|
| `all` | (every backend) | Fanned-out search; ACL Anthology prioritised |
| `arxiv` | `ArxivBackend` | Physics, math, CS, and other preprints |
| `dblp` | `DblpBackend` | Computer science bibliography |
| `semantic_scholar` | `SemanticScholarBackend` | Broad academic search |
| `acl_anthology` | `ACLAnthologyBackend` | ACL / EMNLP / NAACL and related venues |

## License

MIT — see [`LICENSE`](../LICENSE). Authored by Ivan Vykopal.
