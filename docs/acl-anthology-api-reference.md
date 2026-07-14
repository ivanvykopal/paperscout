# ACL Anthology Search API — Reference for Building a Python Client

This documents the HTTP API exposed by the **ACL Anthology Search API** service (a
FastAPI app in this repo). It is written as a reference for building a Python
package that queries the service to find ACL Anthology papers by keyword or
semantic similarity.

The service indexes the full ACL Anthology corpus (~128k papers) and provides:

- **Keyword search** — SQLite FTS5 (Porter-stemmed, BM25-ranked) over titles and abstracts.
- **Similarity search** — cosine similarity over precomputed embeddings (FAISS index).
- **Paper lookup** — fetch a single paper's metadata + canonical BibTeX + PDF URL by id.

All endpoints return JSON.

---

## 1. Base URL & transport

| Environment   | Base URL                                             | Notes                          |
|---------------|------------------------------------------------------|--------------------------------|
| HF Space      | `https://<owner>-<space-name>.hf.space`              | Serves on port 7860 (default). |
| Local dev     | `http://localhost:8000`                              | `python -m app` (reload on).   |

The space subdomain depends on the `HF_SPACE_ID` secret configured in the repo.
Treat the base URL as a client configuration value (do not hardcode it).

- **Scheme:** `https` (HF Space) / `http` (local dev).
- **Auth:** none. The service is read-only and holds all credentials (HF token,
  embedding API key) server-side. A client does **not** need to authenticate.
- **Content type:** all responses are `application/json`. Query-string params
  must be URL-encoded (e.g. spaces as `%20`).
- **No CORS restrictions to worry about for a server-side Python client.**
  Browser-based JS clients should confirm CORS headers before relying on the API.

### Readiness model (important)

On startup the service downloads a snapshot (FAISS index + SQLite DB) and loads
it into memory (~1.3 GB index + ~300 MB DB). Until loading completes, **every
route except `/health` returns `503`** with `{"detail": "service not ready"}`.
Clients must treat `503` as "retry shortly", not as a hard error.

---

## 2. Endpoints

### 2.1 `GET /health`

Liveness + readiness probe. Safe to call before the snapshot is loaded.

**Query parameters:** none.

**Responses:**

- `200` — service is ready.
  ```json
  {
    "status": "ok",
    "index_size": 128618,
    "last_synced_at": "2026-07-04T15:06:00.654970+00:00"
  }
  ```
- `503` — snapshot not yet loaded. Body: `{"detail": "index/db not loaded"}`.

**Field semantics:**

| Field            | Type             | Meaning                                                       |
|------------------|------------------|---------------------------------------------------------------|
| `status`         | `string`         | `"ok"` when ready.                                            |
| `index_size`     | `integer`        | Number of vectors in the FAISS index (= number of embedded papers). |
| `last_synced_at` | `string \| null` | ISO-8601 timestamp of the last corpus sync. `null` until the first sync has run. |

---

### 2.2 `GET /search/keyword`

Keyword (lexical) search over paper titles and abstracts via SQLite FTS5.

**Query parameters:**

| Param   | Type      | Default | Required | Notes                                              |
|---------|-----------|---------|----------|----------------------------------------------------|
| `q`     | `string`  | —       | yes      | Raw FTS5 query. See §3 for syntax.                 |
| `limit` | `integer` | `10`    | no       | Max number of results to return.                   |

**Response:** `200` — a JSON array of `PaperResult` objects (see §4), ordered by
BM25 rank (best match first). Empty array `[]` when nothing matches.

```json
[
  {
    "id": "N18-3011",
    "title": "Attention Is All You Need",
    "abstract": "…",
    "authors": "Ashish Vaswani, Noam Shazeer, …",
    "venue": "NLP",
    "year": 2017,
    "url": "https://aclanthology.org/N18-3011/",
    "bibtex": "@inproceedings{…}",
    "pdf_url": "https://aclanthology.org/N18-3011.pdf"
  }
]
```

**Status codes:**

| Code | When                                                                          |
|------|-------------------------------------------------------------------------------|
| `200`| Success (includes an empty array when there are no matches).                  |
| `422`| Missing `q`, or `limit` is not an integer. FastAPI validation error.          |
| `500`| Malformed FTS5 query (e.g. unbalanced parentheses, unterminated `"quote"`). SQLite raises an FTS5 syntax error, which surfaces as a server error. **Sanitize queries client-side** (see §3, §6). |
| `503`| Snapshot not yet loaded.                                                      |

**Notes:**

- The API does **not** enforce upper/lower bounds on `limit`. `limit=0` returns
  `[]`; negative values are passed straight to SQLite and behave per SQLite's
  `LIMIT` semantics (e.g. `-1` means *no limit*, returning every match — do not
  send negative values). A robust client clamps `limit` to `[0, N]` (e.g. `0..100`).
- Inactive (retracted) papers are excluded from results.
- There is no pagination — use `limit` to cap result size.

---

### 2.3 `GET /search/similarity`

Embedding-similarity (semantic) search. The query text is embedded via the
external embedding API, then matched against the FAISS index (cosine similarity
over normalized vectors). Results are sorted by descending similarity.

**Query parameters:**

| Param | Type      | Default | Required | Notes                                          |
|-------|-----------|---------|----------|------------------------------------------------|
| `q`   | `string`  | —       | yes      | Free-text query. **No FTS5 syntax** — pass natural language. |
| `k`   | `integer` | `10`    | no       | Number of nearest neighbors to return.         |

**Response:** `200` — a JSON array of `SimilarityResult` objects (a `PaperResult`
plus a `score` field), ordered by descending `score`.

```json
[
  {
    "id": "N18-3011",
    "title": "…",
    "abstract": "…",
    "authors": "…",
    "venue": "…",
    "year": 2017,
    "url": "https://aclanthology.org/N18-3011/",
    "bibtex": "@inproceedings{…}",
    "pdf_url": "https://aclanthology.org/N18-3011.pdf",
    "score": 0.8123
  }
]
```

| Code | When                                                                              |
|------|-----------------------------------------------------------------------------------|
| `200`| Success.                                                                          |
| `422`| Missing `q`, or `k` is not an integer.                                            |
| `500`| Upstream embedding API failure. The service retries transient failures (timeouts/connection errors) up to 3 times with a 2 s backoff; a hard failure (non-transient error, or exhaustion of retries) surfaces as a server error. **Retriable on the client side** with backoff. |
| `503`| Snapshot not yet loaded.                                                          |

**Field semantics:**

- `score` — cosine similarity in `[-1, 1]`; higher is more similar. There is no
  fixed threshold for "relevant"; calibrate on your own queries.

**Latency note:** this is the only endpoint that makes an outbound call at
request time (to embed the query). Expect higher and more variable latency than
keyword search, and occasional `500`s if the embedding service is degraded.

---

### 2.4 `GET /paper/{paper_id}`

Metadata lookup by ACL Anthology paper id.

**Path parameter:**

| Param       | Type     | Example            | Notes                                                       |
|-------------|----------|--------------------|-------------------------------------------------------------|
| `paper_id`  | `string` | `N18-3011`, `2023.acl-long.123` | The globally-unique anthology id (`Paper.full_id`). |

**Response:** `200` — a single `PaperResult` object (shape as in §4), including
the canonical `bibtex` entry and the direct `pdf_url`.

```json
{
  "id": "1993.tc-1.6",
  "title": "Terminology and the computer - attention shifts to the micro",
  "abstract": "…",
  "authors": "Warren Weaver",
  "venue": "TC",
  "year": 1993,
  "url": "https://aclanthology.org/1993.tc-1.6/",
  "bibtex": "@inproceedings{weaver-1993-terminology,\n  title = …}",
  "pdf_url": "https://aclanthology.org/1993.tc-1.6.pdf"
}
```

**Status codes:**

| Code | When                                                                          |
|------|-------------------------------------------------------------------------------|
| `200`| Found.                                                                        |
| `404`| Unknown id, or the paper is inactive (retracted). Body: `{"detail": "paper not found"}`. |
| `503`| Snapshot not yet loaded.                                                      |

**Notes:**

- The id is case-sensitive (anthology ids use the casing above).
- Inactive papers are treated as not found.

---

## 3. FTS5 query syntax (for `/search/keyword`)

`q` is passed directly to SQLite FTS5 (Porter-stemmed tokenizer). Spaces
**AND** terms. Supported operators:

| Construct                 | Meaning                                   | Example                                  |
|---------------------------|-------------------------------------------|------------------------------------------|
| `term1 term2`             | AND both terms                            | `transformer attention`                  |
| `"exact phrase"`          | Consecutive-word phrase match             | `"neural machine"`                       |
| `prefix*`                 | Prefix / wildcard match                   | `translat*`                              |
| `term1 OR term2`          | Either term                               | `attention OR transformer`              |
| `term1 NOT term2`         | `term1` and not `term2`                   | `transformer NOT survey`                |
| `( ... )`                 | Grouping                                  | `(attention OR transformer) NOT survey`  |

**Examples:**

```
q=transformer attention
q="neural machine"
q=translat*
q=(attention OR transformer) NOT survey
```

**Gotchas for a client:**

- **Malformed queries cause `500`.** Unbalanced parens, unterminated quotes, or a
  stray `*`/`NOT` can raise an FTS5 syntax error server-side. A robust client
  should either (a) validate/sanitize the query before sending, or (b) fall back
  to a simpler query (e.g. strip operators, quote phrases) on `500`.
- **Stemming:** `translat*` and `translation` both match `translation`,
  `translator`, `translating`, etc. Porter stemming is applied automatically.
- **No field filtering** in the public query surface: FTS5 searches across
  `title` *and* `abstract`. There is no `title:`/`abstract:` field qualifier
  exposed.
- The API does **not** support filtering by year, venue, or author — fetch more
  results with `limit` and filter client-side.

---

## 4. Data model

### `PaperResult`

| Field     | Type             | Always present? | Meaning                                                                 |
|-----------|------------------|-----------------|-------------------------------------------------------------------------|
| `id`      | `string`         | yes             | Globally-unique anthology id, e.g. `2023.acl-long.1` (`Paper.full_id`). |
| `title`   | `string`         | yes             | Paper title (plain text; anthology markup stripped).                   |
| `abstract`| `string`         | yes             | Abstract (plain text). Empty string `""` when the anthology has none.  |
| `authors` | `string`         | yes             | Comma-separated `First Last` names. Empty string when no authors.      |
| `venue`   | `string`         | yes             | Venue acronym from the parent collection (e.g. `ACL`, `NAACL`, `NLP`). May be empty. |
| `year`    | `integer \| null`| yes             | Publication year. `null` when the anthology has no year for the paper.  |
| `url`     | `string`         | yes             | Canonical anthology page URL (`Paper.web_url`). May be empty.          |
| `bibtex`  | `string`         | yes             | Canonical ACL Anthology BibTeX entry. Empty string `""` when there is no citable entry (e.g. some frontmatter). |
| `pdf_url` | `string`         | yes             | Direct PDF URL (`Paper.pdf.url`). Empty string `""` when no PDF reference. |

### `SimilarityResult`

A `PaperResult` with one additional field:

| Field   | Type     | Meaning                                            |
|---------|----------|----------------------------------------------------|
| `score` | `float`  | Cosine similarity in `[-1, 1]`; higher = more similar. |

### `HealthResponse`

| Field            | Type             | Meaning                                              |
|------------------|------------------|------------------------------------------------------|
| `status`         | `string`         | `"ok"` when ready.                                  |
| `index_size`     | `integer`        | Number of vectors in the FAISS index.               |
| `last_synced_at` | `string \| null` | ISO-8601 timestamp of last sync; `null` until first sync. |

---

## 5. Error model

All error responses use FastAPI/Starlette's `{"detail": ...}` shape, except
validation errors (`422`) which return a richer structure, and unhandled server
errors (`500`) which return a plain-text body.

| Status | Body shape                                                         | Typical cause                                       |
|--------|--------------------------------------------------------------------|-----------------------------------------------------|
| `422`  | `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`        | Missing required param, or non-integer `limit`/`k`.|
| `404`  | `{"detail": "paper not found"}`                                    | Unknown/inactive `paper_id` on `/paper/{id}`.       |
| `503`  | `{"detail": "service not ready"}` (non-`/health`) or `{"detail": "index/db not loaded"}` (`/health`) | Snapshot still loading on startup. |
| `500`  | `Internal Server Error` (plain text)                              | Malformed FTS5 query, or upstream embedding-API failure. Retriable. |

**Client retry policy (recommended):**

- `503` → retry with exponential backoff (snapshot is loading; usually clears in seconds-to-minutes on cold start).
- `500` on `/search/similarity` → retry with backoff (transient embedding-API issues already retried server-side, but a hard failure may still be transient on the network path).
- `500` on `/search/keyword` → **do not blindly retry the same query**: it is likely a malformed FTS5 query. Sanitize and retry once, then surface the error.
- `422`, `404` → do not retry; fix the request.

---

## 6. Building a Python client — guidance

### 6.1 Recommended stack

- **HTTP:** `httpx` (sync or async, supports timeouts and retries cleanly).
- **Models:** `pydantic` (matches the server's own models and gives validation).
- **Retries:** `tenacity` (exponential backoff, per-status retry predicates).

### 6.2 Suggested model definitions

```python
from pydantic import BaseModel

class Paper(BaseModel):
    id: str
    title: str
    abstract: str
    authors: str
    venue: str
    year: int | None = None
    url: str
    bibtex: str = ""
    pdf_url: str = ""

class SimilarityPaper(Paper):
    score: float

class Health(BaseModel):
    status: str
    index_size: int
    last_synced_at: str | None = None
```

### 6.3 Minimal client sketch

```python
import httpx
from urllib.parse import quote_plus

class ACLAnthologyClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self._base = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self._base, timeout=timeout)

    def health(self) -> dict:
        r = self._client.get("/health")
        r.raise_for_status()
        return r.json()

    def keyword_search(self, query: str, limit: int = 10) -> list[dict]:
        limit = max(0, min(int(limit), 100))  # clamp; avoid negative (SQLite LIMIT -1 = unlimited)
        params = {"q": query, "limit": limit}
        r = self._client.get("/search/keyword", params=params)
        if r.status_code == 500:
            # likely a malformed FTS5 query — surface a clear error
            raise ValueError(f"Malformed FTS5 query: {query!r}") from None
        r.raise_for_status()
        return r.json()

    def similarity_search(self, query: str, k: int = 10) -> list[dict]:
        k = max(0, min(int(k), 100))
        params = {"q": query, "k": k}
        r = self._client.get("/search/similarity", params=params)
        r.raise_for_status()  # caller retries 5xx with backoff
        return r.json()

    def get_paper(self, paper_id: str) -> dict:
        r = self._client.get(f"/paper/{paper_id}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def close(self):
        self._client.close()
```

### 6.4 Client-side considerations

- **Wait for readiness.** On first contact (or after a deploy/space restart),
  poll `/health` until `200` before issuing search requests; otherwise every
  search returns `503`.
- **URL-encode `q`.** When constructing requests manually, encode the query.
  (`httpx`'s `params=` does this automatically — prefer it over f-strings.)
- **Sanitize FTS5 input** for `/search/keyword` if accepting user-supplied
  queries: strip/escape stray `"`, `(`, `)`, `*`, and `NOT`/`OR` tokens you did
  not intend, or wrap the whole query in quotes for a phrase search. On `500`,
  fall back to a quoted phrase.
- **No auth, no rate limits exposed.** The service is intended for a small
  number of users. Be a polite client: avoid tight loops, reuse one HTTP
  connection, and add small delays between burst requests.
- **Filtering / pagination.** Neither is server-side. To filter by year/venue/
  author, fetch a larger `limit`/`k` and filter the returned list client-side.
- **Citing.** Use the returned `bibtex` directly for citations; `pdf_url` for
  downloading full texts. Both can be empty — handle that gracefully.

---

## 7. Quick `curl` reference

```bash
BASE="https://<owner>-<space-name>.hf.space"   # or http://localhost:8000

# readiness
curl "$BASE/health"

# keyword search (BM25 over title + abstract)
curl "$BASE/search/keyword?q=transformer%20attention&limit=5"

# phrase / prefix / boolean FTS5 queries
curl "$BASE/search/keyword?q=%22neural%20machine%22"
curl "$BASE/search/keyword?q=translat*"
curl "$BASE/search/keyword?q=(attention%20OR%20transformer)%20NOT%20survey"

# semantic similarity search
curl "$BASE/search/similarity?q=attention%20mechanism&k=5"

# single paper lookup
curl "$BASE/paper/N18-3011"
```

---

## 8. What the API does *not* provide

When scoping your package, note these gaps (there is no server-side support for):

- Filtering by year, venue, author, or DOI.
- Pagination / cursor-based result iteration.
- Author disambiguation or author-centric search.
- Full-text search (only title + abstract are indexed).
- Bulk / batch fetch of many paper ids in one call.
- Sorting results by anything other than the endpoint's default order (BM25 rank
  for keyword, similarity score for semantic).
- Guaranteed availability SLA — it runs on free-tier infrastructure.

Implement any of the above in the client package as needed.
