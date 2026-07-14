# ACL Anthology Backend — Migrate to HTTP API

**Date:** 2026-07-14
**Status:** Draft
**Package:** paperscout v0.2.2

## Overview

Replace the local, iteration-based ACL Anthology backend with an HTTP client that
talks to the ACL Anthology Search API service. The existing `acl-anthology`
Python package is kept as a degraded fallback when the API is unreachable.

The target service is deployed at `https://ivykopal-acl-api.hf.space` and
exposes `/health`, `/search/keyword`, `/search/similarity`, and `/paper/{id}`
as documented in `docs/acl-anthology-api-reference.md`.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| API transport | HTTP client (`requests`) | Reuses the project's existing `requests` dependency; lighter than loading the full anthology locally. |
| Base URL | `https://ivykopal-acl-api.hf.space` default, configurable via constructor arg or `PAPERSCOUT_ACL_API_URL` env var | Hardcodes the known HF Space while allowing local dev/testing. |
| Search strategy | Similarity first, then keyword, then merge/deduplicate | User preference; reduces load vs. concurrent calls and gives semantic matches priority. |
| Fallback | HTTP API first, local `acl-anthology` package second | Keeps the backend usable offline or during API outages. |
| 503 readiness | Retry with exponential backoff inside the HTTP client (total cumulative wait up to `max_retry_wait`) | Reference doc describes this as a normal startup state; callers should not need to handle it. |
| 500 errors | Fall back to local backend | Any server error (including malformed FTS5) rolls back to the local package. |
| Dependency model | Keep `acl-anthology` as an optional fallback dependency | Users who only want the API path can skip installing it. |

## Architecture

### Component layout

```
paperscout/backends/acl_anthology.py
├── _ACLAnthologyHTTPClient
│   ├── health()
│   ├── search_similarity(query, k)
│   ├── search_keyword(query, limit)
│   ├── get_paper(paper_id)
│   ├── download_pdf(pdf_url, save_path)
│   └── _request_with_retry(...)          # 503 backoff, transient retry
├── _ACLAnthologyLocalBackend
│   ├── search(query, limit)
│   ├── download(identifier, **kwargs)
│   └── _format_result(...)
└── ACLAnthologyBackend  (public facade)
    ├── search(query, limit=10)
    ├── download(identifier, **kwargs)
    └── _try_http_then_local(...)
```

### Public interface

`ACLAnthologyBackend` keeps its existing signature so that `PaperSearcher`,
`PaperDownloader`, and CLI users are unaffected.

```python
backend = ACLAnthologyBackend(
    api_key=None,                # unused; kept for BaseBackend compat
    base_url=None,               # defaults to env var or HF Space
    timeout=30.0,
    max_retry_wait=30.0,
)

papers: list[Paper] = backend.search("attention is all you need", limit=10)
result: dict = backend.download("N18-3011", output_dir="./downloads")
```

### Files modified

| File | Change |
|------|--------|
| `paperscout/backends/acl_anthology.py` | Refactor into HTTP client + local backend + facade. |
| `pyproject.toml` | Move `acl-anthology` to a soft optional dependency; ensure HTTP library (`httpx` or reuse `requests`) is available. |
| `requirements.txt` | Mirror pyproject changes if needed. |
| `tests/test_backends.py` | Update/expand tests for HTTP path, local fallback, retry behavior, and result mapping. |

### Files unchanged

- `paperscout/backends/base.py`
- `paperscout/backends/__init__.py`
- `paperscout/types.py`
- `paperscout/search.py`
- `paperscout/download.py`
- `paperscout/client.py`
- `paperscout/cli.py`

## Data Flow

### Search

1. Facade receives `search(query, limit)`.
2. HTTP client calls `GET /search/similarity?q={query}&k={limit}`.
3. On success, it then calls `GET /search/keyword?q={query}&limit={limit}`.
4. Each response is parsed into a list of API `PaperResult` objects.
5. Results are merged and deduplicated by `id`.
   - If a paper appears in both lists, keep the higher `similarity`/`score`.
6. The merged list is truncated to `limit` and sorted by score descending.
7. Each item is mapped to the internal `Paper` dataclass.
8. If similarity search fails entirely, the facade falls back to
   `_ACLAnthologyLocalBackend.search(...)`. If similarity succeeds but keyword
   search fails, return the merged/deduplicated similarity results without
   falling back to the local backend.

### API-to-`Paper` mapping

| API field | Internal `Paper` field | Transformation |
|-----------|------------------------|----------------|
| `id` | `identifier` | As-is. |
| `title` | `title` | As-is; strip whitespace. |
| `authors` (string) | `authors` (list) | Split on `, `; empty string → `[]`. |
| `year` | `year` | `null` → `None`. |
| `abstract` | `abstract` | As-is; empty string stays empty. |
| `venue` | `categories` | Wrap in list: `[venue]` or `[]` if empty. |
| `url` | `url` | As-is. |
| `pdf_url` | `pdf_url` | As-is; empty string stays empty. |
| `score` (similarity only) | `similarity` | Keyword results get their score from `_title_similarity` after mapping, or `None`. |
| `bibtex` | — | Not stored on `Paper` for now; returned by the API but unused internally. |

### Download

1. Facade receives `download(identifier, output_dir=...)`.
2. HTTP client calls `GET /paper/{identifier}`.
3. On success, use the returned `pdf_url` to download the PDF to `output_dir`.
4. Return dict with `status: success`, `identifier`, `path`, `filename`, `title`,
   `authors`, `source: acl_anthology`.
5. On API failure, fall back to `_ACLAnthologyLocalBackend.download(...)`.

## Error Handling

### HTTP client retry policy

| Scenario | Behavior |
|----------|----------|
| `503 service not ready` | Retry with exponential backoff up to `max_retry_wait` (default 30 s). |
| `500` on `/search/similarity` | Retry once after a short delay; if still failing, raise to facade for fallback. |
| `500` on `/search/keyword` | Do not retry; raise to facade, which falls back to local backend. |
| `404` on `/paper/{id}` | No retry; return "paper not found" error dict. |
| Network timeout / connection error | Retry once or twice with backoff, then raise to facade. |
| `422` validation error | No retry; raise to facade, which falls back to local backend. |

### Facade fallback

- If the HTTP client raises after exhausting retries and no usable results have
  been collected yet, the facade logs a warning and tries
  `_ACLAnthologyLocalBackend` when `acl-anthology` is installed.
- If similarity search returned results but keyword search failed, the facade
  returns the similarity results without falling back.
- If the local backend is unavailable, the facade returns:
  - `search(...)`: empty list `[]`.
  - `download(...)`: error dict `{"status": "error", "message": "..."}`.

### Logging

- Use the standard `logging` module.
- Log fallback events at `WARNING` level.
- Log retry events at `DEBUG` level.

## Testing Plan

### New / updated tests in `tests/test_backends.py`

| Test | Coverage |
|------|----------|
| `test_acl_http_search_uses_api` | Mocks `/search/similarity` and `/search/keyword`; asserts sequential calls, merge, deduplication, and mapping to `Paper`. |
| `test_acl_http_search_similarity_only` | Simulates keyword endpoint failure; asserts similarity results are still returned. |
| `test_acl_http_search_falls_back_to_local` | Simulates API `500` and asserts local backend is used. |
| `test_acl_http_search_no_local_backend` | Simulates API failure with `acl-anthology` not installed; asserts empty list. |
| `test_acl_http_download_uses_api` | Mocks `/paper/{id}` + PDF download; asserts success dict. |
| `test_acl_http_download_falls_back_to_local` | API failure triggers local download fallback. |
| `test_acl_http_503_retries` | Asserts `503` triggers retries with backoff. |
| `test_acl_http_result_mapping` | Verifies API `authors` string → list, `venue` → `categories`, `year: null` → `None`. |

### Manual verification checklist

- [ ] `paperscout search "attention is all you need" --source acl_anthology` returns results.
- [ ] `paperscout download N18-3011` succeeds.
- [ ] With API unreachable, results still come from local backend (if installed).
- [ ] With API unreachable and `acl-anthology` not installed, graceful empty/error response.

### Existing tests

No changes expected for `test_search.py`, `test_similarity.py`, `test_client.py`,
or `test_markdown_refs.py`.

## Scope Boundaries

**In scope:**

- Refactor `ACLAnthologyBackend` to call the HTTP API first.
- Add internal HTTP client with retry/backoff and result mapping.
- Preserve local `acl-anthology` package as a fallback.
- Update/add tests for the new behavior.
- Update dependency metadata in `pyproject.toml` / `requirements.txt`.

**Out of scope:**

- Changing other backends (arxiv, dblp, semantic_scholar).
- Adding new CLI flags or changing CLI behavior.
- Caching API responses.
- Bulk/batch paper lookup.
- Advanced FTS5 query sanitization beyond the API reference guidance.
