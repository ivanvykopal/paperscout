"""
Field-level grounding of bibliographic references.

A reference is grounded by finding the published record(s) it refers to and
checking every cited field against them independently:

- title    word-level diff (catches swapped words such as "Few-Shot" -> "Zero-Shot")
- authors  name matching in both directions (invented, missing, reordered authors)
- year     against every known version of the work (arXiv vs. proceedings)
- venue    canonicalised venue names (NeurIPS == NIPS, Findings != main conference)
- doi      resolved via doi.org; must exist and point to the cited work
- arxiv    resolved via the arXiv API; must exist and point to the cited work

Verdicts (worst field wins):

- ``verified``      every checked field agrees with the record
- ``review``        record found; small differences worth a look (off-by-one year,
                    subtitle omitted, venue not confirmable, ...)
- ``mismatch``      record found but a field is wrong (likely partially hallucinated)
- ``not_found``     no source knows a work with this title (likely hallucinated)
- ``unverifiable``  lookups failed or the reference has no title; nothing can be concluded
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sqlite3
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any
from difflib import SequenceMatcher
from pathlib import Path

from paperscout.backends.crossref import normalize_doi
from paperscout.types import Paper

VERDICTS = ("verified", "review", "mismatch", "not_found", "unverifiable")
DEFAULT_SOURCES = ["crossref", "dblp", "semantic_scholar", "arxiv", "acl_anthology"]

# Field status, ordered by severity.
MATCH, UNCHECKED, MINOR, UNCONFIRMED, ERROR, MISMATCH = (
    "match", "unchecked", "minor", "unconfirmed", "error", "mismatch",
)
_SEVERITY = {MATCH: 0, UNCHECKED: 0, MINOR: 1, UNCONFIRMED: 1, ERROR: 1, MISMATCH: 2}


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #


@dataclass
class Reference:
    """A cited reference as written in the paper."""

    title: str
    authors: list[str] = field(default_factory=list)
    authors_truncated: bool = False  # "and others" / "et al." in the citation
    year: int | None = None
    venue: str = ""
    doi: str = ""
    arxiv_id: str = ""
    key: str = ""  # BibTeX key, if any
    raw: str = ""  # original citation text, if any


@dataclass
class FieldCheck:
    """Outcome of comparing one cited field against the record."""

    field: str
    status: str
    cited: str
    found: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "status": self.status,
            "cited": self.cited,
            "found": self.found,
            "note": self.note,
        }


@dataclass
class GroundingResult:
    """Verdict and per-field evidence for one reference."""

    reference: Reference
    verdict: str
    checks: list[FieldCheck] = field(default_factory=list)
    matched: Paper | None = None
    versions: list[Paper] = field(default_factory=list)
    closest: Paper | None = None
    title_similarity: float = 0.0
    source_errors: dict[str, str] = field(default_factory=dict)
    sources_queried: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def issues(self) -> list[str]:
        """Human-readable problems, most severe first."""
        bad = [c for c in self.checks if _SEVERITY[c.status] > 0]
        bad.sort(key=lambda c: -_SEVERITY[c.status])
        out = [f"{c.field}: {c.note}" for c in bad]
        if self.note:
            out.insert(0, self.note)
        return out

    @property
    def doi(self) -> str:
        """Best known DOI of the matched work (prefers non-arXiv DOIs)."""
        dois = [p.doi for p in self.versions if p.doi]
        dois.sort(key=lambda d: d.lower().startswith("10.48550/"))
        return dois[0] if dois else ""

    def to_dict(self) -> dict:
        ref = self.reference
        return {
            "key": ref.key,
            "verdict": self.verdict,
            "issues": self.issues,
            "reference": {
                "title": ref.title,
                "authors": ref.authors,
                "authors_truncated": ref.authors_truncated,
                "year": ref.year,
                "venue": ref.venue,
                "doi": ref.doi,
                "arxiv_id": ref.arxiv_id,
                "raw": ref.raw,
            },
            "checks": [c.to_dict() for c in self.checks],
            "title_similarity": round(self.title_similarity, 3),
            "matched_paper": self.matched.to_dict() if self.matched else None,
            "versions": [
                {"source": p.source, "identifier": p.identifier, "year": p.year,
                 "venue": p.venue, "doi": p.doi, "url": p.url}
                for p in self.versions
            ],
            "closest_paper": self.closest.to_dict() if self.closest else None,
            "sources_queried": self.sources_queried,
            "source_errors": self.source_errors,
        }


# --------------------------------------------------------------------------- #
# Text normalisation
# --------------------------------------------------------------------------- #

_LATEX_SPECIAL = {
    r"\ss": "ss", r"\o": "o", r"\O": "O", r"\l": "l", r"\L": "L",
    r"\ae": "ae", r"\AE": "AE", r"\oe": "oe", r"\aa": "a", r"\AA": "A", r"\i": "i",
}
_LATEX_ACCENT = re.compile(r"\\[`'^\"~=.uvHcdbkr]\s*\{?\s*(\\?[A-Za-z])\s*\}?")
_LATEX_FORMAT = re.compile(r"\\(?:emph|textit|textbf|textsc|textrm|texttt|mathrm|mathbf|text|url)\s*\{([^{}]*)\}")


def strip_latex(text: str) -> str:
    """Remove LaTeX markup, accents and grouping braces."""
    if not text:
        return ""
    s = text
    for _ in range(3):  # nested formatting
        s = _LATEX_FORMAT.sub(r"\1", s)
    s = _LATEX_ACCENT.sub(lambda m: m.group(1).lstrip("\\"), s)
    for cmd, repl in _LATEX_SPECIAL.items():
        s = re.sub(re.escape(cmd) + r"(?![A-Za-z])\s*", repl, s)
    s = s.replace(r"\&", "&").replace("~", " ").replace("--", "-")
    s = re.sub(r"\\[A-Za-z]+\s*", " ", s)
    s = s.replace("{", "").replace("}", "").replace("\\", "")
    return re.sub(r"\s+", " ", s).strip()


def fold(text: str) -> str:
    """Lowercase ASCII-folded text without LaTeX or HTML markup."""
    s = strip_latex(html.unescape(text or ""))
    s = re.sub(r"<[^>]+>", "", s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("ø", "o").replace("ł", "l").replace("ß", "ss").replace("æ", "ae")
    return s.lower().replace("&", " and ")


def normalize_title(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", " ", fold(title))
    return " ".join(s.split())


# --------------------------------------------------------------------------- #
# Title
# --------------------------------------------------------------------------- #

_TITLE_STOPWORDS = {
    "a", "an", "the", "of", "for", "on", "in", "to", "and", "with", "from", "by",
    "via", "at", "as", "is", "are",
}


def _stem(word: str) -> str:
    if len(word) > 3 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def title_similarity(a: str, b: str) -> float:
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb or na.replace(" ", "") == nb.replace(" ", ""):
        return 1.0
    return SequenceMatcher(None, na, nb, autojunk=False).ratio()


def _main_title(title: str) -> str:
    return normalize_title(re.split(r"[:?]\s", title, maxsplit=1)[0])


def compare_titles(cited: str, found: str) -> FieldCheck:
    nc, nf = normalize_title(cited), normalize_title(found)
    check = FieldCheck("title", MATCH, cited, found)
    if nc == nf or nc.replace(" ", "") == nf.replace(" ", ""):
        return check

    main_c, main_f = _main_title(cited), _main_title(found)
    if main_c and main_f and (main_c == nf or nc == main_f):
        check.status = MINOR
        check.note = "subtitle omitted or added"
        return check

    tc = [_stem(w) for w in nc.split()]
    tf = [_stem(w) for w in nf.split()]
    removed: list[str] = []
    added: list[str] = []
    spelling_only = True
    for op, i1, i2, j1, j2 in SequenceMatcher(None, tc, tf, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        seg_c, seg_f = tc[i1:i2], tf[j1:j2]
        removed += seg_c
        added += seg_f
        if op != "replace" or len(seg_c) != len(seg_f) or any(
            SequenceMatcher(None, x, y).ratio() < 0.8 for x, y in zip(seg_c, seg_f)
        ):
            spelling_only = False

    significant = [w for w in removed + added if w not in _TITLE_STOPWORDS]
    if not significant:
        check.status = MINOR
        check.note = "differs only in stopwords or plural forms"
    elif spelling_only:
        check.status = MINOR
        check.note = f"spelling differs: '{' '.join(removed)}' vs '{' '.join(added)}'"
    else:
        check.status = MISMATCH
        parts = []
        if removed:
            parts.append(f"cited has '{' '.join(removed)}'")
        if added:
            parts.append(f"record has '{' '.join(added)}'")
        check.note = "title altered: " + ", ".join(parts)
    return check


# --------------------------------------------------------------------------- #
# Authors
# --------------------------------------------------------------------------- #

_PARTICLES = {
    "van", "von", "der", "den", "de", "del", "della", "dei", "di", "da", "dos", "das",
    "du", "la", "le", "ter", "ten", "bin", "ibn", "al", "el", "st", "zu", "af",
}
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}


@dataclass(frozen=True)
class Name:
    raw: str
    last: str  # folded, particles kept, no spaces/punctuation
    first: str  # folded given names
    tokens: frozenset

    @property
    def initial(self) -> str:
        return self.first[:1]


def parse_name(raw: str) -> Name:
    s = fold(raw)
    s = re.sub(r"\s+\d{4}$", "", s.strip())  # DBLP disambiguation suffix "Wei Wang 0001"
    if "," in s:
        parts = [p.strip() for p in s.split(",") if p.strip()]
        parts = [p for p in parts if re.sub(r"[^a-z]", "", p) not in _SUFFIXES] or parts
        last_part, first_part = parts[0], " ".join(parts[1:])
        last_tokens = re.findall(r"[a-z]+", last_part)
        first_tokens = re.findall(r"[a-z]+", first_part)
    else:
        toks = [t for t in re.findall(r"[a-z][a-z'\-]*", s) if t.strip("-'") not in _SUFFIXES]
        toks = [re.sub(r"[^a-z]", "", t) for t in toks]
        toks = [t for t in toks if t]
        if len(toks) <= 1:
            first_tokens, last_tokens = [], toks
        else:
            split = len(toks) - 1
            for i in range(1, len(toks) - 1):
                if toks[i] in _PARTICLES:
                    split = i
                    break
            first_tokens, last_tokens = toks[:split], toks[split:]
    last = "".join(last_tokens)
    return Name(raw=raw, last=last, first=" ".join(first_tokens),
                tokens=frozenset(first_tokens + last_tokens))



def name_match(a: Name, b: Name) -> str | None:
    """Return 'exact', 'variant' (same surname, first initial differs) or None."""
    if not a.last or not b.last:
        return None
    same_last = a.last == b.last or (
        min(len(a.last), len(b.last)) >= 4 and (a.last.endswith(b.last) or b.last.endswith(a.last))
    )
    if not same_last:
        # given/family order swapped (common for East Asian names) or hyphenation
        joined_a, joined_b = "".join(sorted(a.tokens)), "".join(sorted(b.tokens))
        if a.tokens and (a.tokens == b.tokens or joined_a == joined_b):
            return "exact"
        if a.first and b.first and a.first.replace(" ", "") == b.last and b.first.replace(" ", "") == a.last:
            return "exact"
        return None
    if a.initial and b.initial and a.initial != b.initial:
        return "variant"
    return "exact"


def compare_authors(cited: list[str], truncated: bool, found: list[str]) -> FieldCheck:
    check = FieldCheck(
        "authors", MATCH,
        "; ".join(cited) + ("; et al." if truncated else ""),
        "; ".join(found),
    )
    if not cited:
        check.status, check.note = UNCHECKED, "no authors in citation"
        return check
    if not found:
        check.status, check.note = UNCHECKED, "record lists no authors"
        return check

    c_names = [parse_name(a) for a in cited]
    f_names = [parse_name(a) for a in found]
    used: set[int] = set()
    assignment: list[int | None] = []
    variants: list[str] = []
    for cn in c_names:
        best, best_kind = None, None
        for j, fn in enumerate(f_names):
            if j in used:
                continue
            kind = name_match(cn, fn)
            if kind == "exact":
                best, best_kind = j, kind
                break
            if kind == "variant" and best is None:
                best, best_kind = j, kind
        assignment.append(best)
        if best is not None:
            used.add(best)
            if best_kind == "variant":
                variants.append(f"'{cn.raw}' vs '{f_names[best].raw}'")

    problems: list[str] = []
    minor: list[str] = []
    invented = [c_names[i].raw for i, j in enumerate(assignment) if j is None]
    if invented:
        problems.append(f"not authors of this work: {', '.join(invented)}")
    if not truncated:
        omitted = [f_names[j].raw for j in range(len(f_names)) if j not in used]
        if omitted:
            shown = ", ".join(omitted[:5]) + (f" (+{len(omitted) - 5} more)" if len(omitted) > 5 else "")
            problems.append(f"omits {len(omitted)} author(s): {shown}")
    if assignment[0] is not None and assignment[0] != 0:
        problems.append(f"first author should be {f_names[0].raw}")
    matched_order = [j for j in assignment if j is not None]
    if matched_order != sorted(matched_order) and not any("first author" in p for p in problems):
        minor.append("author order differs")
    if variants:
        minor.append("given name differs: " + "; ".join(variants))

    if problems:
        check.status = MISMATCH
        check.note = "; ".join(problems + minor)
    elif minor:
        check.status = MINOR
        check.note = "; ".join(minor)
    return check


def author_agreement(cited: list[str], found: list[str]) -> float:
    """Fraction of cited authors present in the record (used for candidate selection)."""
    if not cited or not found:
        return 0.0
    f_names = [parse_name(a) for a in found]
    hits = sum(1 for a in cited if any(name_match(parse_name(a), fn) for fn in f_names))
    return hits / len(cited)


# --------------------------------------------------------------------------- #
# Year
# --------------------------------------------------------------------------- #


def compare_year(cited: int | None, versions: list[Paper]) -> FieldCheck:
    years = sorted({p.year for p in versions if p.year})
    check = FieldCheck("year", MATCH, str(cited or ""), ", ".join(map(str, years)))
    if cited is None:
        check.status, check.note = UNCHECKED, "no year in citation"
    elif not years:
        check.status, check.note = UNCHECKED, "record has no year"
    elif cited not in years:
        gap = min(abs(cited - y) for y in years)
        if gap == 1:
            check.status = MINOR
            check.note = f"cited {cited}, record says {check.found} (preprint vs. publication year?)"
        else:
            check.status = MISMATCH
            check.note = f"cited {cited}, record says {check.found}"
    return check


# --------------------------------------------------------------------------- #
# Venue
# --------------------------------------------------------------------------- #

# Order matters: specific conferences before the generic "association for
# computational linguistics" pattern.
_VENUES: list[tuple[str, list[str]]] = [
    ("arxiv", [r"\barxiv\b", r"^corr\b", r"\bcorr abs\b", r"\bpreprint\b"]),
    ("tacl", [r"\btacl\b", r"transactions of the association for computational linguistics"]),
    ("emnlp", [r"\bemnlp\b", r"empirical methods in natural language processing"]),
    ("naacl", [r"\bnaacl\b", r"north american chapter of the association for computational linguistics"]),
    ("eacl", [r"\beacl\b", r"european chapter of the association for computational linguistics"]),
    ("aacl", [r"\baacl\b", r"asia pacific chapter of the association for computational linguistics", r"\bijcnlp\b"]),
    ("coling", [r"\bcoling\b", r"international conference on computational linguistics"]),
    ("lrec", [r"\blrec\b", r"language resources and evaluation"]),
    ("conll", [r"\bconll\b", r"computational natural language learning"]),
    ("semeval", [r"\bsemeval\b", r"semantic evaluation"]),
    ("acl", [r"\bacl\b", r"annual meeting of the association for computational linguistics",
             r"association for computational linguistics"]),
    ("cl", [r"^computational linguistics$", r"^j$"]),
    ("neurips", [r"\bneurips\b", r"\bnips\b", r"neural information processing systems"]),
    ("icml", [r"\bicml\b", r"international conference on machine learning"]),
    ("iclr", [r"\biclr\b", r"international conference on learning representations"]),
    ("aaai", [r"\baaai\b"]),
    ("ijcai", [r"\bijcai\b", r"international joint conference on artificial intelligence"]),
    ("cvpr", [r"\bcvpr\b", r"computer vision and pattern recognition"]),
    ("iccv", [r"\biccv\b", r"international conference on computer vision"]),
    ("eccv", [r"\beccv\b", r"european conference on computer vision"]),
    ("kdd", [r"\bkdd\b", r"knowledge discovery and data mining"]),
    ("www", [r"^www\b", r"the web conference", r"world wide web conference"]),
    ("sigir", [r"\bsigir\b", r"research and development in information retrieval"]),
    ("wsdm", [r"\bwsdm\b", r"web search and data mining"]),
    ("cikm", [r"\bcikm\b", r"information and knowledge management"]),
    ("jmlr", [r"\bjmlr\b", r"journal of machine learning research"]),
    ("tmlr", [r"\btmlr\b", r"transactions on machine learning research"]),
    ("colm", [r"\bcolm\b", r"conference on language modeling"]),
    ("icwsm", [r"\bicwsm\b", r"weblogs and social media"]),
    ("tpami", [r"\btpami\b", r"pattern analysis and machine intelligence"]),
    ("nature", [r"^nature$"]),
    ("science", [r"^science$"]),
]
_CHAPTER_VENUES = {"acl", "emnlp", "naacl", "eacl", "aacl"}


def canonical_venue(venue: str) -> str | None:
    """Map a venue string to a canonical id, or None if unknown/workshop."""
    s = re.sub(r"[^a-z0-9]+", " ", fold(venue)).strip()
    if not s:
        return None
    if "workshop" in s or re.search(r"\bws\b", s):
        return None
    for canon, patterns in _VENUES:
        if any(re.search(p, s) for p in patterns):
            if "findings" in s and canon in _CHAPTER_VENUES:
                return f"findings-{canon}"
            return canon
    if s.startswith("findings"):
        return "findings-acl"
    return None


def _venue_tokens(venue: str) -> set[str]:
    s = re.sub(r"[^a-z]+", " ", fold(venue))
    drop = _TITLE_STOPWORDS | {"proceedings", "conference", "annual", "meeting", "international",
                               "volume", "long", "short", "papers", "th", "st", "nd", "rd"}
    return {w for w in s.split() if w not in drop and len(w) > 1}


def compare_venue(cited: str, versions: list[Paper]) -> FieldCheck:
    record_venues = list(dict.fromkeys(p.venue for p in versions if p.venue))
    check = FieldCheck("venue", MATCH, cited, "; ".join(record_venues))
    if not cited.strip():
        check.status, check.note = UNCHECKED, "no venue in citation"
        return check
    if not record_venues:
        check.status, check.note = UNCONFIRMED, "no record lists a venue"
        return check

    cc = canonical_venue(cited)
    record_canon = {canonical_venue(v) for v in record_venues}
    peer_reviewed = {c for c in record_canon if c and c != "arxiv"}

    if cc and cc in record_canon:
        return check
    if cc is None:
        cited_tokens = _venue_tokens(cited)
        for v in record_venues:
            vt = _venue_tokens(v)
            if cited_tokens and vt and len(cited_tokens & vt) / min(len(cited_tokens), len(vt)) >= 0.8:
                return check
        check.status = UNCONFIRMED
        check.note = f"could not confirm '{cited}'; records list: {check.found}"
        return check
    if cc == "arxiv":
        check.status = MINOR
        check.note = f"cited as preprint; also published at {', '.join(sorted(peer_reviewed)) or check.found}"
        return check
    if not peer_reviewed:
        check.status = UNCONFIRMED
        check.note = f"cited {cc}; only found {check.found}"
        return check
    check.status = MISMATCH
    check.note = f"cited {cc}; published at {', '.join(sorted(peer_reviewed))}"
    return check


# --------------------------------------------------------------------------- #
# Identifier extraction
# --------------------------------------------------------------------------- #

_ARXIV_NEW = r"\d{4}\.\d{4,5}(?:v\d+)?"
_ARXIV_OLD = r"[a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?"
ARXIV_RE = re.compile(
    rf"(?:arxiv(?:\.org/(?:abs|pdf)/|:\s*|\s+preprint\s+arxiv:\s*|\s+)|10\.48550/arxiv\.)({_ARXIV_NEW}|{_ARXIV_OLD})",
    re.IGNORECASE,
)
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>{}]+)", re.IGNORECASE)


def extract_arxiv_id(*texts: str) -> str:
    for text in texts:
        if not text:
            continue
        m = ARXIV_RE.search(text)
        if m:
            return re.sub(r"v\d+$", "", m.group(1))
    return ""


def extract_doi(*texts: str) -> str:
    for text in texts:
        if not text:
            continue
        m = DOI_RE.search(text)
        if m:
            return normalize_doi(m.group(1).rstrip(".,;)]"))
    return ""


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #


def default_cache_path() -> Path:
    base = os.environ.get("PAPERSCOUT_CACHE_DIR") or os.path.join(
        os.environ.get("XDG_CACHE_HOME") or os.path.join(Path.home(), ".cache"), "paperscout"
    )
    return Path(base) / "grounding.sqlite"


class ResponseCache:
    """SQLite cache of successful lookups so re-runs are fast and rate-limit friendly."""

    def __init__(self, path: Path | str | None = None, ttl_days: float = 30.0):
        self.path = Path(path) if path else default_cache_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl_days * 86400
        self._lock = threading.Lock()
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, t REAL, v TEXT)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    @staticmethod
    def _key(kind: str, source: str, query: str) -> str:
        return hashlib.sha256(f"{kind}\0{source}\0{query}".encode()).hexdigest()

    def get(self, kind: str, source: str, query: str):
        with self._lock, self._connect() as db:
            row = db.execute("SELECT t, v FROM cache WHERE k = ?", (self._key(kind, source, query),)).fetchone()
        if not row or time.time() - row[0] > self.ttl:
            return None
        return json.loads(row[1])

    def put(self, kind: str, source: str, query: str, value) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO cache VALUES (?, ?, ?)",
                (self._key(kind, source, query), time.time(), json.dumps(value)),
            )


# --------------------------------------------------------------------------- #
# Grounder
# --------------------------------------------------------------------------- #

SAME_WORK_TITLE = 0.90  # title similarity at which a record is considered the same work
ALTERED_TITLE = 0.70  # lower bound when authors also agree (catches altered titles)
_MISSING = {"__missing__": True}


class Grounder:
    """Ground references against Crossref, DBLP, Semantic Scholar, arXiv and ACL Anthology."""

    def __init__(
        self,
        sources: list[str] | None = None,
        searcher=None,
        cache: ResponseCache | None = None,
        use_cache: bool = True,
        limit: int = 5,
    ):
        if searcher is None:
            from paperscout.search import PaperSearcher

            searcher = PaperSearcher()
        self.searcher = searcher
        self.sources = list(sources) if sources else list(DEFAULT_SOURCES)
        unknown = [s for s in self.sources if s not in searcher.BACKENDS]
        if unknown:
            raise ValueError(f"Unknown source(s): {', '.join(unknown)}. Available: {', '.join(searcher.BACKENDS)}")
        self.cache = (cache or ResponseCache()) if use_cache else None
        self.limit = limit

    # -- lookups --------------------------------------------------------- #

    def _search(self, source: str, query: str) -> list[Paper]:
        if self.cache:
            hit = self.cache.get("search", source, query)
            if hit is not None:
                return [Paper.from_dict(d) for d in hit]
        papers = self.searcher._get_backend(source).search(query, limit=self.limit)
        for p in papers:
            p.source = source
        if self.cache:
            self.cache.put("search", source, query, [p.to_dict() for p in papers])
        return papers

    def _lookup(self, source: str, identifier: str) -> Paper | None:
        if self.cache:
            hit = self.cache.get("lookup", source, identifier)
            if hit is not None:
                return None if hit == _MISSING else Paper.from_dict(hit)
        paper = self.searcher._get_backend(source).lookup(identifier)
        if self.cache:
            self.cache.put("lookup", source, identifier, paper.to_dict() if paper else _MISSING)
        return paper

    # -- main entry ------------------------------------------------------ #

    def _run(self, jobs: dict[str, tuple]) -> tuple[dict[str, Any], dict[str, str]]:
        """Execute (kind, source, query) jobs concurrently; collect outcomes and errors."""
        outcomes: dict[str, Any] = {}
        errors: dict[str, str] = {}
        if not jobs:
            return outcomes, errors
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = {
                name: pool.submit(self._search if kind == "search" else self._lookup, src, q)
                for name, (kind, src, q) in jobs.items()
            }
            for name, fut in futures.items():
                try:
                    outcomes[name] = fut.result()
                except Exception as e:  # noqa: BLE001 - recorded and surfaced in the verdict
                    errors[name] = f"{type(e).__name__}: {e}"[:300]
        return outcomes, errors

    @staticmethod
    def _fallback_queries(ref: Reference, sources: list[str]) -> dict[str, tuple]:
        """Author-driven queries that can surface the real work behind an altered title."""
        surnames = [parse_name(a).last for a in ref.authors[:3]]
        surnames = [s for s in surnames if s]
        if not surnames:
            return {}
        year = str(ref.year or "")
        queries = {
            "dblp": " ".join(surnames + ([year] if year else [])),
            "crossref": " ".join(surnames + [ref.title, year]).strip(),
            "semantic_scholar": f"{ref.title} {surnames[0]}",
        }
        return {f"{s}+authors": ("search", s, q) for s, q in queries.items() if s in sources}

    def ground(self, ref: Reference) -> GroundingResult:
        if not normalize_title(ref.title):
            return GroundingResult(ref, "unverifiable", note="reference has no title")

        jobs: dict[str, tuple] = {s: ("search", s, ref.title) for s in self.sources}
        if ref.doi:
            jobs["doi"] = ("lookup", "crossref", normalize_doi(ref.doi))
        if ref.arxiv_id:
            jobs["arxiv_id"] = ("lookup", "arxiv", ref.arxiv_id)
        outcomes, errors = self._run(jobs)

        candidates: list[Paper] = []
        for s in self.sources:
            candidates.extend(outcomes.get(s) or [])

        checks: list[FieldCheck] = []
        id_records: list[Paper] = []
        for name, label in (("doi", "doi"), ("arxiv_id", "arxiv")):
            if name not in jobs:
                continue
            cited_id = ref.doi if name == "doi" else ref.arxiv_id
            if name in errors:
                checks.append(FieldCheck(label, ERROR, cited_id, note=f"lookup failed ({errors[name]})"))
                continue
            record = outcomes.get(name)
            if record is None:
                checks.append(FieldCheck(label, MISMATCH, cited_id, note="identifier does not exist"))
                continue
            tcheck = compare_titles(ref.title, record.title)
            if tcheck.status == MISMATCH and title_similarity(ref.title, record.title) < SAME_WORK_TITLE:
                checks.append(FieldCheck(label, MISMATCH, cited_id, record.title,
                                         note=f"identifier resolves to a different paper: '{record.title}'"))
                continue
            checks.append(FieldCheck(label, MATCH, cited_id, record.title))
            id_records.append(record)

        scored = [(title_similarity(ref.title, p.title), p) for p in candidates + id_records]
        same = _same_work(ref, scored, id_records)
        if not same and ref.authors:
            extra, extra_errors = self._run(self._fallback_queries(ref, self.sources))
            for name, papers in extra.items():
                if name.split("+")[0] not in errors:
                    scored += [(title_similarity(ref.title, p.title), p) for p in papers or []]
            same = _same_work(ref, scored, id_records)
            for name, err in extra_errors.items():
                errors.setdefault(name.split("+")[0], err)

        result = GroundingResult(
            ref, "verified", sources_queried=list(self.sources),
            source_errors={k: v for k, v in errors.items() if k in self.sources},
        )

        if not same:
            result.checks = checks
            if scored:
                result.title_similarity, result.closest = max(scored, key=lambda x: x[0])
            failed = [s for s in self.sources if s in errors]
            if failed and len(failed) == len(self.sources):
                result.verdict = "unverifiable"
                result.note = "every source failed; rerun later"
            elif failed:
                result.verdict = "unverifiable"
                result.note = (f"no match in reachable sources, but {', '.join(failed)} failed; "
                               "rerun later or exclude the failing source with --source")
            else:
                result.verdict = "not_found"
                result.note = "no source has a work with this title"
            return result

        # Primary record: best title; other versions of the work inform year/venue.
        best_sim = max(sim for sim, _ in same)
        versions = [p for sim, p in same if sim >= min(best_sim, SAME_WORK_TITLE) or p in id_records]
        versions = _dedupe(versions)
        primary = max(versions, key=lambda p: (title_similarity(ref.title, p.title),
                                               author_agreement(ref.authors, p.authors), len(p.authors)))

        title_check = compare_titles(ref.title, primary.title)
        author_checks = [compare_authors(ref.authors, ref.authors_truncated, p.authors)
                         for p in versions if p.authors]
        author_check = min(author_checks, key=lambda c: _SEVERITY[c.status]) if author_checks else \
            compare_authors(ref.authors, ref.authors_truncated, [])

        result.checks = [title_check, author_check, compare_year(ref.year, versions),
                         compare_venue(ref.venue, versions)] + checks
        result.matched = primary
        result.versions = versions
        result.title_similarity = best_sim

        worst = max(_SEVERITY[c.status] for c in result.checks)
        result.verdict = {0: "verified", 1: "review", 2: "mismatch"}[worst]
        return result


def _same_work(ref: Reference, scored: list[tuple[float, Paper]], id_records: list[Paper]) -> list[tuple[float, Paper]]:
    """Candidates that are the cited work, possibly with an altered title.

    A record qualifies if its title is near-identical, it was reached through the
    cited DOI/arXiv ID, or its title is fairly similar and the cited authors and
    year agree (this is what exposes altered titles instead of "not found").
    """
    same = []
    for sim, p in scored:
        if sim >= SAME_WORK_TITLE or p in id_records:
            same.append((sim, p))
        elif sim >= ALTERED_TITLE and (
            (ref.authors and author_agreement(ref.authors, p.authors) >= 0.5
             and (not ref.year or not p.year or abs(ref.year - p.year) <= 1))
            or _main_title(ref.title) in (normalize_title(p.title), _main_title(p.title))
        ):
            same.append((sim, p))
    return same


def _dedupe(papers: list[Paper]) -> list[Paper]:
    seen, out = set(), []
    for p in papers:
        key = (p.source, p.identifier or p.title)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out
