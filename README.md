# paperscout

A multi-purpose tool for searching, downloading, and managing academic papers.

[![PyPI version](https://badge.fury.io/py/paperscout.svg)](https://badge.fury.io/py/paperscout)
[![Python versions](https://img.shields.io/pypi/pyversions/paperscout.svg)](https://pypi.org/project/paperscout/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- **Search papers** across multiple sources using pluggable backends
- **Download papers** by DOI or arXiv ID
- **Programmatic API** and **CLI** interface
- **Backend architecture** for easy addition of new sources
- **Smart title matching** - searches across title and abstract

## Installation

```bash
pip install paperscout
```

### With all backend support

```bash
pip install paperscout[arxiv]
# or install all optional dependencies
pip install paperscout[all]
```

Available backend extras:
- `arxiv` - arXiv backend using arxivy
- `dblp` - DBLP backend using dblpcli
- `s2cli` - Semantic Scholar backend using s2cli
- `acl-anthology` - ACL Anthology backend

## Backend Architecture

The package uses a backend architecture where each source has its own backend implementation:

```
paperscout/
├── backends/
│   ├── base.py              # Base backend class (abstract)
│   ├── arxiv.py             # arXiv backend using arxivy
│   ├── dblp.py              # DBLP backend using dblpcli
│   ├── s2cli.py             # Semantic Scholar backend using s2cli
│   └── acl_anthology.py     # ACL Anthology backend
├── similarity.py            # Title similarity functions
├── search.py                # Searcher using backends
├── client.py                # Client using searchers
└── formatter.py             # Rich formatting for CLI output
```

To add a new backend:
1. Create a new module in `backends/` (e.g., `pubmed.py`)
2. Implement the `BaseBackend` abstract class
3. Register it in `PaperSearcher.BACKENDS`

## CLI Usage

### Commands

| Command | Description |
|---------|-------------|
| `search` | Search for papers across sources |
| `match` | Get the best matching paper by title |
| `download` | Download a paper |

### Search Papers

```bash
# Search all backends (default - ACL Anthology has priority)
paperscout search "Attention Is All You Need"

# Search specific source
paperscout search "Transformer" --source arxiv
paperscout search "Attention" --source acl_anthology

# Limit results
paperscout search "quantum computing" --limit 20

# Output as JSON
paperscout search "query" --json

# Save to file
paperscout search "query" --output results.txt
```

### Get Best Match

```bash
# Get the single best matching paper
paperscout match "Attention Is All You Need"

# Specify source
paperscout match "Transformer" --source arxiv

# JSON output
paperscout match "query" --json
```

### Download Paper

The identifier type is auto-detected — no need to specify `--source`:

```bash
# Download by arXiv ID (auto-detected)
paperscout download arXiv:2301.12345

# Download by bare arXiv ID
paperscout download 2301.12345

# Download by DOI (auto-detected, tries multiple backends)
paperscout download 10.18653/v1/P18-1001

# Download by ACL Anthology ID
paperscout download P18-1001

# Specify source explicitly (if needed)
paperscout download P18-1001 --source acl_anthology

# Specify output directory for the PDF
paperscout download arXiv:2301.12345 --output ./papers

# JSON output
paperscout download arXiv:2301.12345 --json
```

## Python API

### Using the Client

```python
from paperscout import PaperFinderClient

# Create client
client = PaperFinderClient()

# Search for papers (ACL Anthology has priority)
results = client.search("Attention Is All You Need", source="all", limit=10)
for paper in results:
    print(f"{paper['title']} - {paper['authors']}")

# Search specific source only
results = client.search("Transformer", source="arxiv", limit=5)

# Download a paper (identifier type auto-detected)
client.download("arXiv:2301.12345", output_dir="./papers")
client.download("10.18653/v1/P18-1001")        # DOI
client.download("P18-1001", source="acl_anthology")  # ACL Anthology ID
```

### Using Backends Directly

```python
from paperscout.backends.acl_anthology import ACLAnthologyBackend
from paperscout.backends.arxiv import ArxivBackend
from paperscout.backends.dblp import DblpBackend
from paperscout.backends.s2cli import SemanticScholarBackend

# Use ACL Anthology backend
backend = ACLAnthologyBackend()
results = backend.search("Attention Is All You Need", limit=10)

# Use arXiv backend
arxiv_backend = ArxivBackend()
papers = arxiv_backend.search("quantum computing", limit=5)

# Download from any backend
backend.download("arXiv:2301.12345")
```

### Searching by Similarity

```python
from paperscout.search import PaperSearcher
from paperscout.similarity import _title_similarity

searcher = PaperSearcher()

# Search all backends with exact match priority
results = searcher.search("Transformer", exact_match_first=True)

# Calculate title similarity
similarity = _title_similarity(
    "Attention Is All You Need",
    "Attention Is All You Need"
)
print(similarity)  # 1.0 for exact match
```

## Sources

| Source | Backend | Description |
|--------|---------|-------------|
| `all` | Multiple | Searches all backends (ACL Anthology has priority) |
| `arxiv` | ArxivBackend | Preprints in physics, math, CS, and more |
| `dblp` | DblpBackend | Computer science bibliography |
| `semantic_scholar` | SemanticScholarBackend | Academic paper search |
| `acl_anthology` | ACLAnthologyBackend | ACL/EMNLP/NAACL papers |
| `crossref` | CrossrefBackend | DOI-registered journals and proceedings; DOI resolution via doi.org |

## BibTeX Support

### Export Papers as BibTeX

```bash
# Search and export as BibTeX
paperscout search "Attention Is All You Need" --bibtex

# Save to file
paperscout match "Transformer" --bibtex --output citations.bib
```

```python
from paperscout import Paper

paper = Paper(...)
bibtex = paper.to_bibtex()
# or with custom key
bibtex = paper.to_bibtex(entry_key="vaswani2017")
```

### Verify References (hallucination check)

`verify` (BibTeX) and `verify-markdown` (References section of a markdown paper)
ground every reference **field by field** against Crossref, DBLP, Semantic Scholar,
arXiv and the ACL Anthology:

| Field | Check |
|-------|-------|
| title | word-level diff against the record ("Few-Shot" → "Zero-Shot" is caught; casing, punctuation, plurals, omitted subtitle are not errors) |
| authors | both directions: invented authors, omitted authors (unless `and others`/`et al.`), wrong first author, order; diacritics, LaTeX accents, particles and "Last, First" handled |
| year | against every version of the work (arXiv vs. proceedings); off by one → review |
| venue | canonical venues (NeurIPS = NIPS, CoRR = arXiv; Findings ≠ main conference) |
| doi / arXiv ID | resolved directly; must exist and point to the cited paper |

Verdicts (the worst field decides):

| Verdict | Meaning |
|---------|---------|
| 🟢 `verified` | every cited field matches a published record |
| 🟡 `review` | record found; minor differences (off-by-one year, venue not confirmable, spelling) |
| 🟠 `mismatch` | record found but a field is wrong — likely hallucinated metadata |
| 🔴 `not_found` | no source knows this title — likely hallucinated reference |
| ⚪ `unverifiable` | a source failed or the entry has no title; nothing concluded, rerun |

A failing source never turns into `not_found`: if any source errored and no match was
found elsewhere, the verdict is `unverifiable`. The exit code is `1` when any
reference is `mismatch` or `not_found` (usable in CI), `2` when the input has no references.

```bash
paperscout verify references.bib
paperscout verify references.bib --report report.txt --json report.json
# annotated copy; --enrich adds missing doi/url to verified/review entries only
paperscout verify references.bib -o annotated.bib --enrich
# restrict sources (e.g. when one is down)
paperscout verify references.bib --source crossref,semantic_scholar,arxiv
paperscout verify-markdown paper.md --report report.txt
```

Lookups are cached for 30 days in `~/.cache/paperscout/grounding.sqlite`
(override with `PAPERSCOUT_CACHE_DIR`, bypass with `--no-cache`). Set `S2_API_KEY`
for Semantic Scholar rate limits and `PAPERSCOUT_MAILTO` for the Crossref polite pool;
with an API key you can raise `--workers`.

```python
from paperscout import PaperFinderClient

for r in PaperFinderClient().verify_bibtex("references.bib"):
    print(r.reference.key, r.verdict, r.issues)
```

Limitations: a `verified` verdict means the cited metadata matches a real record; it
does not check that the paper supports the claim it is cited for. Works absent from
all sources (books, reports, blogs, very new papers) come out `not_found` and need a
manual look.

## CLI Output

The CLI uses rich formatting for better readability:

- **Tables** for multiple papers showing source, year, title, and authors
- **Panels** for single paper details with full metadata
- **Color coding** for better visual separation
- **Truncation** for long titles and abstracts

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Author

Ivan Vykopal - ivan.vykopal@gmail.com

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## Acknowledgments

- Uses [arxivy](https://github.com/mrshu/arxivy) for arXiv API interactions
- Uses [acl-anthology](https://github.com/acl-org/acl-anthology) for ACL Anthology data
