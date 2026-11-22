# Testing & Verification Manual

How to manually verify each phase of the project, with exact commands and expected output.
Run everything from the repo root (`IntelligenceHub/`).

---

## 0. Setup and service startup

Examples below use a macOS/Linux shell. Output blocks are representative, not captured results: versions, IDs, timings, counts, and log formatting vary. Run each command from the repository root unless stated otherwise.

### 0a. Choose what you want to test

| Test path | What must be running? | What it verifies |
|---|---|---|
| Lint, typecheck, automated tests (§1–2) | Python environment only | Code checks and isolated tests using fixtures/fakes |
| Real indexing (§3–4) | Ollama with `nomic-embed-text` | Real embeddings, SQLite, Chroma, and BM25 |
| API health (§5a) | Uvicorn | HTTP server and application startup |
| Queued API ingestion (§5b–5d) | Ollama, Redis, Uvicorn, Celery worker | End-to-end asynchronous ingestion |
| Retrieval pipeline (§6) | Ollama (`nomic-embed-text` + `llama3.2:3b`), existing indexes | Hybrid retrieval end-to-end |
| Generation / RAG (§7) | Same as §6 | Cited answers, refusals, session memory |
| REST API (§8) | Uvicorn (+ Ollama/indexes for query endpoints) | HTTP surface: query, sources, stats, health, metrics |
| Streamlit UI (§9) | Ollama (both models), Redis, Uvicorn, Celery worker, Streamlit | Chat streaming + citations, source management, filters, analytics, settings |
| Evaluation benchmark (§10) | Ollama (both models; + judge model for `--e2e`), existing indexes | Recall/MRR/NDCG, dense-vs-BM25-vs-hybrid, faithfulness, latency percentiles |
| Production hardening (§11) | Python environment for quality gates; Docker/Compose for container checks | Coverage, lifecycle and real-HTTP tests, full-stack deployment, persistence, CI |

Native development defaults to embedded SQLite and Chroma; Compose runs Chroma as a separate server and sets `CHROMA_HOST=chroma`. An explicit `CHROMA_HOST` also selects the server in native runs. Redis and Celery are **not needed** for the synchronous seed script. The API includes answer-generation endpoints, but merely opening the UI or checking `/api/live` does not require models or indexes. Real chat and evaluation require compatible indexed data plus Ollama. Use §11 for the current hardening workflow; earlier phase notes describe their historical implementation state.

### 0b. Install tools and Python dependencies

On macOS, if Homebrew is already installed and the tools are missing:

```bash
brew install uv ollama redis
```

On Linux, install these tools using their supported installation method or your system package manager. Git is also needed for repository ingestion. Check the commands are available:

```bash
uv --version
ollama --version
git --version
```

Expected: version lines such as `uv <version>` and `git version <version>`. Ollama may warn that it cannot connect until you start the server; that is addressed below.

```bash
uv sync --group dev
uv run python --version
```

Expected: dependency resolution/installation or an `Audited ... packages` message, then `Python 3.x.x` (3.11 or newer). `uv` manages `.venv`; there is no need to activate it when using `uv run`. Initial installation requires internet access.

### 0c. Configure the application

If `.env` does not exist, copy the example without overwriting an existing configuration:

```bash
[ -f .env ] || cp .env.example .env
```

For a fully local run, confirm these values in `.env`:

```dotenv
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text
LLM_MODEL=llama3.2:3b
CHROMA_PERSIST_DIR=./data/chroma
SQLITE_DB_PATH=./data/metadata.db
REDIS_URL=redis://localhost:6379/0
```

BM25 defaults to `./data/bm25_index.pkl`; it can be overridden with `BM25_INDEX_PATH`. Defaults below assume these local storage paths. Use the same configuration and working directory for the seed script, API, worker, and verification commands. Restart long-running processes after changing `.env`.

**Optional isolated smoke-test storage:** to avoid mixing demo data with existing indexes, set all three paths in every terminal used for the smoke test, before starting any application process:

```bash
export SQLITE_DB_PATH=./data/testing/metadata.db
export CHROMA_PERSIST_DIR=./data/testing/chroma
export BM25_INDEX_PATH=./data/testing/bm25_index.pkl
```

Environment variables override `.env`. Use a new directory name if `data/testing` already contains an incompatible index. Do not delete existing data just to run a test.

### 0d. Start Ollama (Terminal A)

Choose **one** way to run Ollama:

- If you installed the macOS app, launch **Ollama** from Applications. It runs in the background.
- If you installed the command-line tool, run:

```bash
ollama serve
```

Leave this terminal open. Expected: server startup logs with a listening address on port `11434`; exact text varies by version. If you see `address already in use`, a server may already be running. Check it instead of launching another copy.

In another terminal, verify connectivity:

```bash
curl -fsS http://localhost:11434
```

Expected:

```text
Ollama is running
```

A connection-refused error means the service has not started or the host/port is wrong. If using a non-default `OLLAMA_BASE_URL`, use that address for these HTTP checks too.

### 0e. Download and verify the embedding model (Terminal B)

Keep Ollama running, then run:

```bash
ollama pull nomic-embed-text
ollama list
```

The pull displays download progress and ends with `success`. The list should contain a row resembling:

```text
NAME                       ID              SIZE      MODIFIED
nomic-embed-text:latest     <model-id>      <size>    <time>
```

Download requires internet access and free disk space. Subsequent local embedding requests use the downloaded model. If you changed `EMBEDDING_MODEL`, pull that exact model instead.

Verify the actual project embedder, not just server reachability:

```bash
uv run python - <<'PY'
from src.indexing.ollama import OllamaEmbedder

vectors = OllamaEmbedder().embed(['pod eviction smoke test'])
print('vectors:', len(vectors), '| dimensions:', len(vectors[0]))
assert len(vectors) == 1 and len(vectors[0]) == 768
print('Ollama embedding check passed')
PY
```

Expected with the default model:

```text
vectors: 1 | dimensions: 768
Ollama embedding check passed
```

This uses `OllamaEmbedder` directly so a failure cannot silently select the fallback model. The first request may take longer while the model loads. `get_embedder()` falls back to sentence-transformers when its Ollama check fails; that is **not** a successful Ollama verification and can create incompatible 384-dimensional vectors.

Optional, for future/manual chat-model experiments only:

```bash
ollama pull llama3.2:3b
ollama run llama3.2:3b 'Reply with a short greeting.'
```

Expected: download finishes with `success`, followed by a generated greeting (wording varies). This is not needed for ingestion or indexing.

### 0f. Start Redis only for queued API ingestion

Choose **one** startup method. On macOS, run it as a background Homebrew service:

```bash
brew services start redis
redis-cli ping
```

Expected: a service-started message (or already-running notice), then:

```text
PONG
```

Alternatively, run `redis-server` in its own terminal and leave it open. Expect a `Ready to accept connections` message; run `redis-cli ping` in another terminal.

If using Docker instead of installing Redis locally:

```bash
docker compose up -d redis
docker compose exec redis redis-cli ping
```

Expected: the Redis container starts and the ping returns `PONG`. Docker Desktop/the Docker daemon must be running. Do not start a second Redis instance on an already occupied port `6379`. If `REDIS_URL` uses another server, verify that configured server instead.

### 0g. Terminal layout for a full local test

| Terminal | Command/purpose | Leave running? |
|---|---|---|
| A | `ollama serve` (unless using the app) | Yes |
| B | Setup, model pull, pytest, seed script, curl checks | No; run commands as needed |
| C | `redis-server` (unless using a background service/container) | Yes, for queued tests |
| D | Uvicorn command in §5a | Yes, for API tests |
| E | Celery worker command in §5b | Yes, for queued tests |

Start Ollama before real ingestion; start Redis and the worker before submitting queued API jobs.

---

## 1. Lint & Typecheck

```bash
uv run ruff check src/ tests/
```
Expected: `All checks passed!`

```bash
uv run mypy src/
```
Expected on a clean typecheck: `Success: no issues found in N source files`. Any `error:` lines and a nonzero exit code mean the check failed; record the actual diagnostics rather than treating pre-existing errors as a pass.

---

## 2. Unit Tests

Run the whole suite:

```bash
uv run pytest -v
```

Or per area:

| Area | Command | Expected |
|---|---|---|
| Chunkers (Phase 2) | `uv run pytest tests/test_chunkers.py -v` | all pass — markdown/code/incident splitting |
| Ingesters | `uv run pytest tests/unit/test_ingesters.py -v` | all pass |
| Code languages | `uv run pytest tests/unit/test_code_languages.py -v` | all pass — tree-sitter lang detection |
| Incidents | `uv run pytest tests/unit/test_incidents.py` | all pass |
| Pipeline (Phase 2) | `uv run pytest tests/test_pipeline.py -v` | all pass — dedup, skip-unchanged, replace-changed |
| Incident pipeline | `uv run pytest tests/test_incident_pipeline.py -v` | all pass |
| Git ingestion | `uv run pytest tests/test_git_ingestion.py -v` | all pass |
| Ingest API | `uv run pytest tests/test_ingest_api.py -v` | all pass |
| **Indexing (Phase 3)** | `uv run pytest tests/test_indexing.py -v` | `test_index_and_query PASSED`, `test_dimension_mismatch_raises PASSED` |
| **Retrieval (Phase 4)** | `uv run pytest tests/test_retrieval.py -v` | 6 pass — RRF fusion, filters, confidence, pipeline wiring |
| **Generation (Phase 5)** | `uv run pytest tests/test_generation.py -v` | 7 pass — context formatting, citations, grounding, memory |
| **API (Phase 6)** | `uv run pytest tests/test_api_query.py tests/test_api_sources_stats.py -v` | 8 pass — query endpoint, SSE stream, sources, stats, health |
| **UI client (Phase 7)** | `uv run pytest tests/unit/test_ui_api_client.py -v` | 4 pass — SSE parsing, stream events, error mapping |
| **BM25 refresh (Phase 7)** | `uv run pytest tests/test_indexing.py -k refresh -v` | 1 pass — reload after another process rebuilds the pickle |

Indexing tests use a `FakeEmbedder` — **no Ollama needed** to run them. Retrieval and generation tests are pure Python with no Ollama or Chroma dependency; `test_pipeline_from_defaults_loads_bm25` uses monkeypatched components.

Representative pytest output:

```text
tests/test_indexing.py::test_index_and_query PASSED
tests/test_indexing.py::test_dimension_mismatch_raises PASSED
...
======================== N passed in T seconds ========================
```

The test count changes as tests are added. Success means exit code `0` and no failures/errors. `FAILED` means an assertion failed; `ERROR` often means fixture setup or an import failed. To stop at the first failure with a shorter traceback:

```bash
uv run pytest -x --tb=short -v
```

These tests exercise isolated fixtures and mocked integrations; they do not prove that a real Ollama server or Celery worker is healthy. Continue with the smoke tests for that.

---

## 3. Phase 3 — Real Indexing Smoke Test (needs Ollama)

### 3a. Ingest the corpus

Complete §0d–0e first. This command **writes** documents/chunks to SQLite and vectors/BM25 to the configured storage paths. It initializes database tables automatically; no manual migration command is needed for this smoke test.

Check local inputs first:

```bash
ls corpus/docs corpus/incidents.json corpus/java
```

Expected: Markdown files/directories, the incidents JSON file, and Java source files/directories. The Git source below also needs network access to clone/fetch the repository. A later run can see upstream changes, so counts are not fixed.

```bash
uv run python scripts/seed_demo_data.py \
  --docs corpus/docs \
  --incidents corpus/incidents.json \
  --repo https://github.com/nolar/kopf \
  --code corpus/java
```

Expected output (one line per source):

```
demo-docs: source_id=1, job_id=1, status=done
demo-incidents: source_id=2, job_id=2, status=done
demo-repository: source_id=3, job_id=3, status=done
demo-java-client: source_id=4, job_id=4, status=done
```

Source/job IDs above are examples for a fresh database, not guaranteed values. Each source should finish with `status=done`; an exception or `ingestion_failed` is a failure. Initial ingestion should log `chunks_indexed`, `bm25_built`, and `ingestion_complete` events (format depends on logging configuration). Unchanged sources can skip embedding on later runs.

Smaller version (Markdown + incidents + Git, without the extra Java source):

```bash
uv run python scripts/seed_demo_data.py --docs corpus/docs --incidents corpus/incidents.json --repo https://github.com/nolar/kopf
```

### 3b. Verify SQLite count == Chroma count

```bash
uv run python -c "
from sqlalchemy import select, func
from src.db.session import SessionLocal
from src.db.models import Chunk
from src.indexing.vector_store import VectorStore

db = SessionLocal()
sqlite_count = db.scalar(select(func.count()).select_from(Chunk))
chroma_count = VectorStore().count()
print('sqlite:', sqlite_count, '| chroma:', chroma_count)
assert sqlite_count == chroma_count, 'INDEX DRIFT!'
print('counts match')
"
```

Expected after ingesting a nonempty corpus (numbers are illustrative):

```text
sqlite: 1234 | chroma: 1234
counts match
```

Both counts should be equal **and greater than zero**. Zero equals zero is not evidence of successful ingestion. Equal counts are a useful sanity check, not proof that every vector ID/content matches.

If counts differ, stop and inspect job errors and configured storage paths. Fewer Chroma vectors can indicate missing indexing; more can indicate orphaned vectors or data from another run. Do not assume that re-ingesting unchanged files will repair a missing index: content-hash deduplication can skip them. Use fresh isolated storage for a clean reproduction and retain the existing data for diagnosis.

### 3c. Verify semantic search returns sensible hits

```bash
uv run python -c "
from src.indexing.vector_store import VectorStore
from src.indexing.embedders import get_embedder

q = get_embedder().embed(['why was my pod evicted'])[0]
res = VectorStore().query(q, top_k=3)
for vid, meta, dist in zip(res['ids'][0], res['metadatas'][0], res['distances'][0]):
    print(f'{dist:.3f}  {vid}  {meta[\"source_path\"]}')
"
```

Representative output shape:

```text
0.245  doc12-chunk0  /path/to/corpus/docs/.../pod-qos.md
0.301  doc34-chunk2  /path/to/corpus/docs/.../disruptions.md
```

Exact paths, IDs, rankings, and distances vary. Inspect whether results discuss pod eviction, resource pressure, QoS, or disruptions; the filenames above are examples, not assertions. Chroma uses cosine distance here: lower is closer. Relevant results provide a semantic-search smoke check, not a retrieval-quality benchmark. Empty results usually mean the selected store has no vectors; a dimension error indicates an incompatible embedding model/index.

### 3d. Verify BM25 keyword index

The BM25 index is pickled to disk after each ingestion. Check it exists:

```bash
ls -lh data/bm25_index.pkl data/chroma/
```

Expected: a nonempty `bm25_index.pkl`; `data/chroma/` contains `chroma.sqlite3` and may contain segment directories. Size/layout vary with corpus size and Chroma version. If using the isolated storage exports, inspect `data/testing/bm25_index.pkl` and `data/testing/chroma/` instead.

`BM25Index.load()` (added in Phase 4) rebuilds the in-memory index from the pickled corpus — verify the persisted index loads and ranks without touching SQLite:

```bash
uv run python - <<'PY'
from src.indexing.bm25 import BM25Index

index = BM25Index()
assert index.load(), 'No persisted BM25 index; ingest the corpus first (§3a)'
hits = index.query('pod eviction', top_k=3)
for vector_id, score in hits:
    print(f'{score:.3f}  {vector_id}')
assert hits and any(score > 0 for _, score in hits), 'No positive keyword matches'
print('BM25 keyword check passed')
PY
```

Expected: up to three score/ID lines and `BM25 keyword check passed` for a corpus containing those terms. Larger BM25 scores rank higher (unlike cosine distance). `load()` returns `False` (with a `bm25_index_missing` warning) when the pickle does not exist — that is a missing-index signal, not a crash. Do not unpickle index files from untrusted sources.

---

## 4. Re-ingestion idempotency check

Run the **same seed command and arguments used in §3a** a second time, with the same paths/configuration. For the smaller command:

```bash
uv run python scripts/seed_demo_data.py --docs corpus/docs --incidents corpus/incidents.json --repo https://github.com/nolar/kopf
```

Expected: `status=done` again; for unchanged sources, `ingestion_complete` reports `skipped` equal to `documents` and `chunks=0`. Log formatting may use JSON fields or `key=value`. Job IDs increase, but source IDs are reused by this script for matching source type/location. Re-run **3b**: both counts should still match and should be unchanged from the first run. If the remote Git repository changed upstream, that source can legitimately add/replace chunks and change counts.

---

## 5. API and asynchronous ingestion checks

### 5a. Start the API (Terminal D)

```bash
uv run uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
```

Leave it running. Representative startup output:

```text
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

Startup initializes SQLite tables. In Terminal B:

```bash
curl -i http://localhost:8000/api/health
```

Expected: HTTP `200 OK` and a deep-health body such as `{"status":"ok","ollama":true,"chroma":true,"sqlite":true,"bm25":true}`. Whitespace/header ordering can differ. `status` is `degraded` when any component probe fails — check the boolean fields to see which. Open `http://localhost:8000/docs` to inspect the currently implemented API routes.

### 5b. Start the worker (Terminal E)

Verify Ollama and Redis as described in §0. Start the API before processing jobs so tables exist. Then, from the same repository root and with matching storage/environment settings:

```bash
uv run celery -A src.tasks.celery_app:celery_app worker --loglevel=info --pool=solo
```

`--pool=solo` is a simple single-process option for local smoke testing, including macOS. Leave the worker running. Expected output includes a Redis broker address, the registered `run_ingestion` task, and a readiness line resembling:

```text
[tasks]
  . run_ingestion
...
celery@<hostname> ready.
```

Repeated broker connection errors mean Redis/configuration needs attention; do not submit jobs until the worker is ready.

### 5c. Submit a job (Terminal B)

This example generates JSON with Python so absolute paths containing spaces are handled correctly:

```bash
uv run python - <<'PY' | curl -sS -i -X POST http://localhost:8000/api/ingest \
  -H 'Content-Type: application/json' --data-binary @-
import json
from pathlib import Path

print(json.dumps({
    'name': 'manual-docs',
    'source_type': 'markdown',
    'location': str(Path('corpus/docs').resolve()),
}))
PY
```

Expected: HTTP `202 Accepted` and a body such as:

```json
{"job_id": 5, "data_source_id": 5, "status": "queued"}
```

Record the returned IDs; yours may differ. `queued` only confirms publication, not successful indexing. This POST creates a new data source each time. To repeat ingestion of the **same** API source, use the refresh endpoint below instead of repeatedly creating sources.

### 5d. Poll and refresh

Replace `5` with your returned job ID:

```bash
curl -sS http://localhost:8000/api/ingest/5
```

An in-progress job can report `queued` or `running`. Repeat until completion. Representative successful response:

```json
{
  "id": 5,
  "status": "done",
  "error": null,
  "started_at": "2026-01-01T10:00:00",
  "completed_at": "2026-01-01T10:00:05"
}
```

Timestamps vary. If `status` is `failed`, inspect `error` and worker logs. A Celery task log saying `succeeded` is not sufficient: the task can successfully return the string `failed`, so check the API job status. A job stuck at `queued` usually means no worker is consuming from the configured broker.

Refresh the existing source (replace `5` with `data_source_id`, not `job_id`):

```bash
curl -sS -X POST http://localhost:8000/api/ingest/sources/5/refresh
```

Expected: a new `job_id`, the same `data_source_id`, and `status=queued`. Poll the new job. Re-run §3b after ingestion to confirm counts still match.

To bypass content-hash dedup and rewrite every chunk (e.g. after the pipeline starts writing new metadata), add `?force=true`. To force re-ingest every source once (needs `jq`):

```bash
for id in $(curl -s localhost:8000/api/sources | jq '.[].id'); do
  curl -s -X POST "localhost:8000/api/ingest/sources/$id/refresh?force=true"; echo
done
```

### 5e. Basic negative API checks

```bash
curl -i http://localhost:8000/api/ingest/0
curl -i -X POST http://localhost:8000/api/ingest \
  -H 'Content-Type: application/json' \
  -d '{"name":"invalid-type-test","source_type":"unknown","location":"unused"}'
```

Expected: HTTP `404` with `{"detail":"Job not found"}`, then HTTP `400` with `{"detail":"Unknown source_type: unknown"}`. Missing required request fields instead produce HTTP `422` validation details.

---

## 6. Phase 4 — Retrieval smoke test (needs Ollama + existing indexes)

Prerequisites: §0d–0e complete, `llama3.2:3b` pulled (`ollama pull llama3.2:3b`), and a corpus already indexed via §3a (`data/chroma/` and `data/bm25_index.pkl` exist and §3b counts match). If you used the isolated-storage exports in §0c, export the same paths in this terminal first.

### 6a. End-to-end pipeline query

`RetrievalPipeline.from_defaults()` wires embedder + Chroma + BM25 + query rewriter + LLM reranker in one call:

```bash
uv run python - <<'PY'
from src.retrieval.pipeline import RetrievalPipeline

pipe = RetrievalPipeline.from_defaults()
results, conf, confident = pipe.retrieve('why was my pod evicted')
print(f'confidence={conf:.3f} confident={confident} results={len(results)}')
for i, r in enumerate(results, 1):
    print(f'[{i}] rrf={r.score:.4f}  {r.metadata.get("vector_id")}  {r.content[:80]!r}')
assert results, 'No results returned; check indexes and corpus'
PY
```

Expected: `confident=True` (on a corpus covering pod eviction), up to `top_k_final=5` results, each line showing an RRF score (~0.01–0.03), a `doc{id}-chunk{i}` vector_id, and a text preview related to the question. Exact content and ordering depend on the corpus. A `bm25_index_missing` warning means the BM25 pickle was not found — dense retrieval still runs, but the hybrid half contributes nothing; verify the `BM25_INDEX_PATH` setting matches §3a.

### 6b. Metadata filter check

```bash
uv run python - <<'PY'
from src.retrieval.filters import RetrievalFilters
from src.retrieval.pipeline import RetrievalPipeline

pipe = RetrievalPipeline.from_defaults()
results, conf, confident = pipe.retrieve(
    'database connection failure',
    filters=RetrievalFilters(source_type='incident'),
)
print(f'filtered results={len(results)} confident={confident}')
for r in results:
    assert r.metadata.get('source_type') == 'incident', \
        f"filter leak: {r.metadata.get('source_type')}"
print('filter check passed')
PY
```

Expected: `filter check passed` — every returned chunk has `source_type='incident'` (assertion fires if filtering leaks). Result count may be 0–5; zero results on a corpus with no matching incidents is correct behavior, not a failure. Valid filter keys: `source_type`, `repository`, `language`, `severity` — matching the metadata written at ingestion.

### 6c. Graceful-degradation check (Ollama down)

The LLM-dependent stages must never break retrieval. Stop Ollama (`Ctrl+C` on `ollama serve`, or quit the app), then run §6a's script again.

Expected: the pipeline still returns results — `query_rewrite_failed` and `rerank_failed_fallback_to_rrf` warnings appear in the logs, the original query is used, and the RRF ordering is preserved. If the **embedder** also fails (`ollama_unavailable_falling_back`), `get_embedder()` swaps to sentence-transformers; a dimension mismatch against a 768-dim index surfaces as an error rather than silently wrong results — restore Ollama to continue. Restart Ollama afterward.

### 6d. Low-confidence check

```bash
uv run python - <<'PY'
from src.retrieval.pipeline import RetrievalPipeline

pipe = RetrievalPipeline.from_defaults()
results, conf, confident = pipe.retrieve('quantum blockchain synergy protocol')
print(f'confidence={conf:.3f} confident={confident} results={len(results)}')
PY
```

Expected: `confident=False` (or a noticeably lower confidence) for a query with no support in the corpus — this is the signal Phase 5 uses to answer "I don't have enough information" instead of hallucinating. `min_confidence_threshold` is a heuristic (0.3); borderline queries may still pass — tune it during Phase 7 evaluation.

---

## 7. Phase 5 — Generation / RAG smoke test (needs Ollama + existing indexes)

Prerequisites: same as §6 — Ollama with `nomic-embed-text` **and** `llama3.2:3b`, plus an indexed corpus (§3a). Construct `RAGGenerator` **once** per process: it owns the `ConversationMemory`, so recreating it per call erases session history.

### 7a. Cited answer on an in-domain question

```bash
uv run python - <<'PY'
from src.generation.generator import RAGGenerator
from src.generation.llm_client import LLMClient
from src.retrieval.pipeline import RetrievalPipeline

rag = RAGGenerator(RetrievalPipeline.from_defaults(), LLMClient())
resp = rag.ask('why was my pod evicted?', session_id='demo')
print(resp.answer)
for s in resp.sources:
    print(f'[{s.index}] {s.path}')
print('confidence:', resp.confidence, '| refused:', resp.refused)
assert not resp.refused, 'Expected a cited answer on an in-domain query'
assert resp.sources, 'Answer has no citation markers'
PY
```

Expected: an answer containing `[1]`, `[2]` markers, a source line per citation with real `source_path` values, `refused: False`, and `confidence` in `high|medium|low`. Exact wording, citation count, and label vary with the corpus and model. An answer with **no** `[n]` markers yields empty `sources` — the assertion then fails; inspect the raw answer (the model may have ignored the citation format rather than the content being wrong).

### 7b. Refusal on an out-of-domain question

```bash
uv run python - <<'PY'
from src.generation.generator import RAGGenerator
from src.generation.llm_client import LLMClient
from src.retrieval.pipeline import RetrievalPipeline

rag = RAGGenerator(RetrievalPipeline.from_defaults(), LLMClient())
resp = rag.ask('quantum blockchain synergy protocol', session_id='demo2')
print(resp.answer, '| refused:', resp.refused, '| confidence:', resp.confidence)
assert resp.refused and not resp.sources
PY
```

Expected: the refusal string ("I don't have enough information in the indexed sources to answer this."), `refused: True`, `confidence: none`, empty `sources`. This is the desired behavior — a RAG system that always answers is a hallucination machine. Low retrieval confidence (§6d) can short-circuit before the LLM is even called.

### 7c. Conversation memory across a follow-up

```bash
uv run python - <<'PY'
from src.generation.generator import RAGGenerator
from src.generation.llm_client import LLMClient
from src.retrieval.pipeline import RetrievalPipeline

rag = RAGGenerator(RetrievalPipeline.from_defaults(), LLMClient())
first = rag.ask('what causes pod eviction?', session_id='demo3')
second = rag.ask('how do I prevent it?', session_id='demo3')  # "it" needs turn 1
print('FIRST:', first.answer[:200])
print('FOLLOW-UP:', second.answer[:200])
assert not second.refused, 'Follow-up refused — memory may not be injected'
PY
```

Expected: the follow-up answers about preventing pod eviction — "it" resolves via the injected history of turn 1. A fresh `session_id` asking "how do I prevent it?" alone should be vaguer or refused — the difference demonstrates memory working. Refusals are intentionally **not** stored in history.

### 7d. Streaming output (optional)

```bash
uv run python - <<'PY'
from src.generation.llm_client import LLMClient

for token in LLMClient().chat_stream(
    [{'role': 'user', 'content': 'Name one cause of pod eviction, one line.'}]
):
    print(token, end='', flush=True)
print()
PY
```

Expected: the answer prints incrementally (token chunks) rather than after a single pause. This is the interface the Phase 7 UI consumes.

---

## 8. Phase 6 — REST API smoke test (needs Uvicorn; Ollama + indexes for query endpoints)

Start the API in its own terminal (same env/storage exports as the data it serves):

```bash
uv run uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
```

Expected startup: `Uvicorn running on http://127.0.0.1:8000` then `Application startup complete`. `/api/query` works without Ollama only in the degraded sense — `get_rag()` builds lazily on first query, so startup itself never needs Ollama.

### 8a. OpenAPI docs and deep health

```bash
curl -sS http://localhost:8000/api/health
```

Expected: `{"status":"ok"|"degraded","ollama":..., "chroma":..., "sqlite":..., "bm25":...}` — every component boolean reported separately. With Ollama stopped, expect `"status":"degraded","ollama":false` while `sqlite` stays `true`. Open `http://localhost:8000/docs` — Swagger UI lists `/api/query`, `/api/query/stream`, `/api/sources`, `/api/stats`, `/api/health`, `/api/analytics/queries`, and the `/api/ingest` routes; `Try it out` on `/api/query` shows the example body. `/metrics` is intentionally absent from the schema.

### 8b. Cited answer over HTTP

```bash
curl -sS -X POST http://localhost:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "why was my pod evicted?", "session_id": "curl-test"}'
```

Expected (corpus-dependent):

```json
{
  "answer": "... evicted under memory pressure [1] ...",
  "sources": [{"index": 1, "vector_id": "doc12-chunk0", "path": "corpus/docs/.../qos.md", "snippet": "..."}],
  "refused": false,
  "confidence": "high",
  "retrieval_confidence": 0.85
}
```

Same query with the same `session_id` builds history — ask `"how do I prevent it?"` next and expect a contextual follow-up. An out-of-domain query returns `refused: true`, `confidence: "none"`, empty `sources`.

### 8c. Negative checks

```bash
curl -sS -i -X POST http://localhost:8000/api/query \
  -H 'Content-Type: application/json' -d '{"query": ""}'
curl -sS -i http://localhost:8000/api/sources/999999
curl -sS -i -X DELETE http://localhost:8000/api/sources/999999
```

Expected: `422` validation error on the empty query (Pydantic, before the handler runs); `404`/`GET` isn't defined on `/api/sources/{id}` so expect `405 Method Not Allowed` for the GET and `404 {"detail":"Data source not found"}` for the DELETE. A `405` vs `404` distinction is normal REST behavior, not a bug.

### 8d. SSE streaming

```bash
curl -N -sS -X POST http://localhost:8000/api/query/stream \
  -H 'Content-Type: application/json' \
  -d '{"query": "what causes OOM kills?"}'
```

Expected: lines arriving incrementally in this order (Phase 7 format — every `data:` payload is JSON):

```text
event: token
data: "Containers are OOM-killed when"

event: token
data: " they exceed their memory limit [1].\n"

event: sources
data: [{"index": 1, "vector_id": "doc12-chunk0", "path": ".../pod-qos.md", "snippet": "...", "score": 0.0325}]

event: done
data: {"confidence": "high", "refused": false, "retrieval_confidence": 0.82}
```

Token text is a JSON string, so newlines appear as `\n` and never break SSE framing. An out-of-domain query emits the refusal token, `sources: []`, then `done` with `"refused": true`. `-N` disables curl buffering so you see tokens live; without it the whole stream appears at once (still correct, just buffered).

### 8e. Sources, stats, and metrics

```bash
curl -sS http://localhost:8000/api/sources
curl -sS http://localhost:8000/api/stats
curl -sS http://localhost:8000/metrics | grep -E 'http_requests_total|http_request_latency'
```

Expected: `/api/sources` is a JSON array with `document_count` per source. `/api/stats` reports `total_chunks`, `chroma_vectors`, and `index_drift` — drift should be `0` on a healthy index (same invariant as §3b). `/metrics` exposes Prometheus text format including `http_requests_total{method="GET",path="/api/stats",status="200"}` — request counts should grow as you hit endpoints. Each API log line in the Uvicorn terminal shows `http_request` with `latency_ms`.

### 8f. Source deletion cleans all three stores (destructive — use a throwaway source)

```bash
# create one via the ingest endpoint, let it finish (§5c–5d), then:
curl -sS -i -X DELETE http://localhost:8000/api/sources/<id>
# verify: sqlite chunk count drops, chroma count drops, bm25 still answers
curl -sS http://localhost:8000/api/stats
```

Expected: `204 No Content`. Re-running §3b's count check still matches (deleted chunks removed from both stores), and keyword queries for that source's terms return fewer/no BM25 hits — the index was rebuilt. Deleting the **last** source removes `bm25_index.pkl` entirely; a subsequent `/api/stats` shows `bm25_loaded: false`.

---

## 9. Phase 7 — Streamlit UI manual test

Prerequisites: everything from §0 running — Ollama with `nomic-embed-text` **and** `llama3.2:3b`, Redis, the API (§5a, Terminal D) and the Celery worker (§5b, Terminal E). Use the same storage paths/exports in every terminal.

> **Re-ingest data created before Phase 7.** Chunks ingested earlier lack `source_type`/`source_path` in `chunk_metadata`, so source filters drop their BM25 hits and some citations show `docN-chunkM` instead of a path. A plain "Re-ingest" does not fix this (unchanged files are skipped by content hash) — use the forced refresh loop in §5d (`?force=true`), which also backfills `repository`/`language`/`severity` metadata.

### 9a. Start the UI (Terminal F)

```bash
uv run streamlit run src/ui/app.py
```

Expected: `You can now view your Streamlit app in your browser. Local URL: http://localhost:8501`, and the browser opens. To point at a different API, either set `API_URL=http://host:port` before starting or change it on the Settings page.

Headless smoke check (no browser, no API needed) — verifies the app script and Chat page render without exceptions:

```bash
uv run python - <<'PY'
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("src/ui/app.py", default_timeout=30).run()
assert not at.exception, [e.value for e in at.exception]
print("UI renders:", [t.value for t in at.title])
PY
```

Expected: `UI renders: ['Ask the Hub']` (warnings about `ScriptRunContext` / `No runtime found` are normal in bare mode).

### 9b. Sidebar and health badge

| # | Action | Expected |
|---|---|---|
| 1 | Open `http://localhost:8501` with all services up | Sidebar shows **Chat / Sources / Analytics / Settings**, title "Engineering Intelligence Hub", green **All systems ok** badge |
| 2 | Stop Ollama, wait ~15 s (health cache TTL), click anything to rerun | Orange **Degraded** badge with caption `Down: ollama` (plus `bm25` if no index exists) |
| 3 | Stop the API (Ctrl+C in Terminal D), wait ~15 s, rerun | Red **API unreachable** badge; pages show `Cannot reach API at http://localhost:8000: ...` errors instead of crashing |
| 4 | Restart Ollama and the API | Badge returns to green within ~15 s |

### 9c. Sources page

| # | Action | Expected |
|---|---|---|
| 1 | Open **Sources** on an empty store | Right column: "Nothing indexed yet. Add a source on the left." |
| 2 | Submit the form with Name empty | Warning "Name and location are both required."; no request sent |
| 3 | Add **Name** `ui-incidents`, **Type** `incident`, **Location** absolute path of `corpus/incidents.json` (`realpath corpus/incidents.json`) | Toast `Queued ingestion job #N`; form clears; "Ingestion jobs" shows a progress bar `#N ui-incidents: pending` → `running` → `done` **without manual refresh** (polled every 2 s) |
| 4 | When the job reaches `done` | Page reruns once by itself; the table lists `ui-incidents` with `source_type=incident` and `document_count > 0`. Worker terminal logs `ingestion_complete` |
| 5 | Repeat with `ui-docs` / `markdown` / absolute path of `corpus/docs` and optionally `ui-java` / `code` / `corpus/java` | Each reaches `done`; table shows one row per source |
| 6 | Add `bad-path` / `markdown` / `/does/not/exist` | Job goes to `failed`, red error box shows the worker's error message |
| 7 | Stop Redis, add any source | Red error `503: Ingestion queue unavailable; retry later`; nothing added to the jobs list. Restart Redis |
| 8 | Select `#<id> ui-docs` in **Manage source**, click **Re-ingest** | New job appears and reaches `done` quickly; worker logs show `skipped` equal to `documents` (unchanged files) |
| 9 | All jobs finished | **Clear finished jobs** button appears; clicking it removes the job list |
| 10 | Select `bad-path`; note **Delete** is disabled; tick **Confirm delete**, click **Delete** | Button only enabled after ticking; row disappears from the table. `curl -sS http://localhost:8000/api/stats` shows `index_drift: 0` |

Docker variant: inside Compose the worker resolves paths in its container — use `/app/corpus/incidents.json`, `/app/corpus/docs`, `/app/corpus/java` (read-only mounts).

### 9d. Chat page — streaming, citations, memory

Streaming is on by default (Settings → **Stream responses**).

| # | Action | Expected |
|---|---|---|
| 1 | Ask `why was my pod evicted?` | Spinner "Retrieving context..." for a few seconds, then the answer types out token by token. Line breaks/markdown in the answer render correctly |
| 2 | After the answer finishes | A confidence badge (**High** green / **Medium** orange / **Low** red), caption `X.Xs · N cited source(s)`, and one expander per citation titled `[n] <real file path>` |
| 3 | Expand a citation | `Fused RRF score: 0.0xxx` caption and the first ~200 chars of the chunk in a wrapped code block. The `[n]` numbers match markers in the answer text |
| 4 | Follow up: `how do I prevent it?` | Contextual answer about preventing eviction — "it" is resolved from the previous turn (server memory keyed by `session_id`) |
| 5 | Ask an out-of-domain question: `quantum blockchain synergy protocol` | "I don't have enough information in the indexed sources to answer this.", grey **Not enough information** badge, `0 cited source(s)` |
| 6 | Navigate to another page and back to Chat | Full conversation is still shown |
| 7 | Click **New conversation** in the sidebar, then ask `how do I prevent it?` | History is cleared; the answer is vague or refused (new `session_id` = no memory) — confirms 9d-4 really used memory |
| 8 | Settings → turn **Stream responses** off; ask `what is a PodDisruptionBudget?` | Spinner "Retrieving context and generating an answer...", then the full answer appears at once with badge + citation cards (served by `/api/query`; cards have no RRF score line) |
| 9 | Stop the API and ask anything | Red error box and an assistant message `Request failed: Cannot reach API ...` with a red **Request failed** badge; the app keeps working. Restart the API |

Cross-check the stream format directly with §8d if the UI shows no citations.

### 9e. Search filters

The sidebar **Source type** filter (Chat page) sends `source_type` with the query.

| # | Action | Expected |
|---|---|---|
| 1 | Set **Incidents**, ask `what caused the outage?` | Every citation path points into `incidents.json` (paths look like `.../incidents.json::id:...`) |
| 2 | Set **Docs**, ask `how do readiness probes work?` | Citations are only Markdown files under `corpus/docs` |
| 3 | Set **Code** (requires a `code` or `git` source), ask `how does the client retry requests?` | Citations are only source-code files |
| 4 | Switch to **Settings** and back to **Chat** | The selected filter is still selected (widget-state persistence) |
| 5 | Set **All sources** | Mixed citation types possible again |

Backend cross-check that BM25 hits survive filtering (requires post-Phase-7 ingestion):

```bash
uv run python - <<'PY'
from src.indexing.bm25 import BM25Index
from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.filters import RetrievalFilters

hits = BM25Retriever(BM25Index()).retrieve("pod eviction memory", 10)
kept = [h for h in hits if RetrievalFilters(source_type="markdown").matches(h)]
print("bm25 hits:", len(hits), "| kept by markdown filter:", len(kept))
print("sample metadata:", hits[0].metadata if hits else None)
assert hits and all("source_type" in h.metadata for h in hits), "re-ingest: metadata missing"
PY
```

Expected: `kept by markdown filter` > 0 and sample metadata containing `source_type` and `source_path`. Before the Phase 7 fix, `kept` was always `0`.

### 9f. BM25 freshness without API restart

| # | Action | Expected |
|---|---|---|
| 1 | With the API already running and a chat already answered, add a new source on **Sources** (e.g. `corpus/java` as `code`) and wait for `done` | — |
| 2 | Without restarting the API, ask a question only that source can answer, with filter **Code** (e.g. `what does ServerSideApply do?`) | Cited answer from the new source. API log shows `bm25_loaded` once (the `refresh()` reload) followed by `bm25_retrieved` with `count > 0` |

If keyword hits appear but dense results for the new source are missing until an API restart, that is the known Chroma multi-process limitation (see `docs/phase-7-ui.md` → Known gaps).

### 9g. Analytics page

| # | Action | Expected |
|---|---|---|
| 1 | Open **Analytics** | **Index** row: Sources / Documents / Chunks (SQLite) / Vectors (Chroma) / Index drift. Chunks == Vectors and drift = `0` |
| 2 | On an empty store | Warning "No BM25 index on disk yet..." |
| 3 | **Server** row | `/api/query` and `/api/query/stream` each show `N requests` and `avg X.XXs`; counts grow after more chats. Stream avg is near zero by design (time-to-first-byte — explained in the caption) |
| 4 | **This browser session** (after ≥ 3 chats) | Queries count, Avg latency, p95 latency, Refusal rate; charts for latency per query, queries per minute, confidence distribution, top query terms; **Raw query log** expander lists each query with latency, confidence, sources, refused, filter |
| 5 | Before any chat in this tab | Info "Ask something on the Chat page to populate these charts." |
| 6 | Reload the browser tab | Session section resets (session-only by design); Index and Server rows persist (server-side) |

### 9h. Settings page

| # | Action | Expected |
|---|---|---|
| 1 | Click **Test connection** | JSON health body `{"status": "ok", "ollama": true, ...}` |
| 2 | Change **API base URL** to `http://localhost:9999`, click **Test connection** | Red "Cannot reach http://localhost:9999"; sidebar badge turns red. Switch to Chat and back — the URL value persisted |
| 3 | Restore `http://localhost:8000` | Badge green again |
| 4 | Set **Request timeout** to `10` and ask a long question on a slow machine | May fail with a `Cannot reach API ... timed out` message — confirms the timeout is applied. Restore `120` |
| 5 | **Session ID** box | Read-only 12-char id; changes after **Start new conversation** |
| 6 | **Model and retrieval** section | Info note that model/temperature/top-k are server-side settings |

### 9i. Docker Compose full stack (optional)

The current Phase 9 stack also includes a Chroma server and a one-shot model initializer; no manual model pulls are required after successful initialization.

```bash
make docker-up
make seed
```

Wait for API liveness before seeding. Expected: `app`, `worker`, `ui`, `ollama`, `chroma`, and `redis` running; health checks pass where configured, while `models` exits with code 0. The optional `seed` service is not normally running. Open `http://localhost:8501` and repeat §9b–9d using absolute worker-visible paths such as `/app/corpus/docs`. See §11d–11g for configuration validation, logs, queue checks, and non-destructive persistence testing.

---

## 10. Phase 8 — Evaluation benchmark (needs Ollama + existing indexes)

Prerequisites: §0d–0e complete, `llama3.2:3b` pulled, and a corpus indexed with **post-Phase-7** metadata (§3a, or a `?force=true` refresh per §5d). The evaluation matches targets on `source_path`/`contains`, which the BM25 leg reads from `chunk_metadata` — chunks ingested before the metadata fix make every BM25 hit count as wrong and skew the comparison. If you used the isolated-storage exports in §0c, export the same paths in this terminal first.

The benchmark talks to the same SQLite/Chroma/BM25 stores as the API — no API process or Redis needed. It does not write to the database.

### 10a. Unit tests for the metrics

```bash
uv run pytest tests/test_eval_metrics.py -v
```

Expected: 5 pass — rank metrics, NDCG with duplicate-chunk dedup, percentile interpolation, target path/contains matching, and a validity check that the golden file loads and has ≥ 50 items. No Ollama needed.

### 10b. Retrieval comparison (dense vs BM25 vs hybrid)

```bash
uv run python -m evaluation.benchmarks.run_benchmark
```

Expected: a `bm25_index_missing`/`parser.error` exit if nothing is ingested; otherwise, after a few minutes (one embed call + two index scans per question × 3 strategies), a markdown report printed to stdout:

```text
# Evaluation report

- date: ...
- questions: 71
- embedder: OllamaEmbedder
- llm: llama3.2:3b
- judge: -
- rrf_k: 60

## Retrieval: dense vs BM25 vs hybrid (RRF)

| strategy | n | recall@5 | recall@10 | mrr | ndcg@10 | p50_s | p90_s | p95_s |
|---|---|---|---|---|---|---|---|---|
| dense | 71 | ... | ... | ... | ... | ... | ... | ... |
| bm25 | 71 | ... | ... | ... | ... | ... | ... | ... |
| hybrid | 71 | ... | ... | ... | ... | ... | ... | ... |

### Recall@10

dense       ##########...                              0.XX
bm25        ##########...                              0.XX
hybrid      ##########...                              0.XX

## Acceptance criteria

- Retrieval Recall@10 > 80% (hybrid): XX.X% — PASS|FAIL
```

and `Saved to evaluation/reports/<timestamp>` containing `results.json` + `report.md`.

Verify: `embedder:` must say `OllamaEmbedder` — `SentenceTransformerEmbedder` here means Ollama was down and results are invalid for the 768-dim index (and would usually have raised a dimension error). Whether hybrid beats the single strategies is a hypothesis to measure, not guaranteed output. Record all strategies even if hybrid loses. If `bm25` shows ~0 across the board, investigate missing `source_path` metadata (§5d force re-ingest) before attributing the result to retrieval quality.

Smoke-check the harness on a few questions first:

```bash
uv run python -m evaluation.benchmarks.run_benchmark --limit 5
```

Inspect failures per question in the report folder:

```bash
uv run python - <<'PY'
import json
rows = json.load(open('evaluation/reports/<timestamp>/results.json'))['retrieval']
misses = [r for r in rows if r['strategy'] == 'hybrid' and r['recall@10'] < 1.0]
for r in misses[:10]:
    print(r['id'], 'recall@10=', r['recall@10'], '| top3:', *r['top3'], sep='\n  ')
PY
```

Expected: each missed item prints its `id` and the three top paths the hybrid retriever actually returned — use this to tell a genuinely wrong ranking from a golden `contains` string that doesn't match the chunk text.

### 10c. End-to-end run (generation + faithfulness + latency)

```bash
uv run python -m evaluation.benchmarks.run_benchmark --e2e
```

Expected: the same retrieval table plus a second section:

```text
## End-to-end (rewrite + hybrid + rerank + generation)

| strategy | n | faithfulness | refused | p50_s | p90_s | p95_s |
|---|---|---|---|---|---|---|
| end-to-end | 71 | 0.8x | 0.0x | X.XX | X.XX | X.XX

## Acceptance criteria

- Retrieval Recall@10 > 80% (hybrid): XX.X% — PASS|FAIL
- Query latency p95 < 5 s: X.XX s — PASS|FAIL
```

This runs the full `RAGGenerator` per question (rewrite + hybrid + rerank + llama3.2:3b), plus a judge call per non-refused answer — expect tens of minutes on a laptop with the 3B model; use `--limit 10` for a quicker check. Interpretation:

- **faithfulness** = fraction of answer claims the judge found supported by cited sources. `1.0` with a high `refused` rate is misleading — read them together.
- **refused** = fraction of questions refused. Some refusals are fine (out-of-corpus questions); a high rate usually means the confidence gate is too strict for your corpus.
- **p95_s** is the number behind the "p95 < 5 s" acceptance criterion. The 3B model on CPU may legitimately exceed it — check whether tokens stream slowly in §8d too before blaming the pipeline.

To use a different judge model (default is `llama3.2:3b` grading its own output):

```bash
ollama pull mistral:7b
uv run python -m evaluation.benchmarks.run_benchmark --e2e --judge-model mistral:7b
```

### 10d. What a passing run looks like

- [ ] `embedder: OllamaEmbedder` in the report header
- [ ] `n` equals the number of dataset items per strategy (71)
- [ ] hybrid `recall@10` and `ndcg@10` ≥ both dense and bm25
- [ ] `Acceptance criteria` shows `PASS` for Recall@10 (hybrid) — or a diagnosed FAIL via the `top3` inspection in §10b
- [ ] `--e2e` shows `PASS` for p95, `refused` consistent with your corpus, `faithfulness` meaningfully > 0
- [ ] `results.json` exists alongside `report.md` in `evaluation/reports/<timestamp>/`

A FAIL is a measurement, not a harness bug — check the misses in `results.json` first (§10b), then the likely suspects in the Troubleshooting table.

---

## 11. Phase 9 — Production hardening

This section verifies the implementation described in [Phase 9 notes](phase-9-production-hardening.md). Commands are repeatable procedures; expected outputs are not evidence that Docker deployment or model benchmarks have passed. Recorded implementation-session results were 85 passing tests, 86.80% combined backend coverage, clean Ruff/mypy, and valid Compose configuration. The image build was blocked by certificate trust; the user is handling full-stack testing.

### 11a. Tooling and command discovery

```bash
uv --version
make help
make setup
```

Expected: uv 0.12.23 or newer locally, the documented command list, and a successful frozen development install. The Docker image and CI currently pin uv 0.12.23. Check the actual error on failure; do not regenerate the lockfile just to make an install green.

For container checks, choose the available Compose executable once in the same terminal:

```bash
if docker compose version >/dev/null 2>&1; then
  compose() { docker compose "$@"; }
else
  compose() { docker-compose "$@"; }
fi
compose version
```

Subsequent `compose ...` examples use this shell function. The Makefile already detects either executable. A working Docker daemon is required for build/startup, not for `make check`.

### 11b. Local quality gates and coverage

```bash
make lint
make typecheck
make test
```

Or run all three in order:

```bash
make check
```

Expected: Ruff reports no issues; mypy reports no issues in `src`; pytest exits 0 and prints total coverage at or above 80%. Exact file/test counts change. The implementation-session observation was **85 passed, 86.80% coverage**, not an expected constant.

`tests/conftest.py` redirects SQLite, Chroma, and BM25 paths to temporary storage before test collection and clears `CHROMA_HOST` so the suite does not use the developer's server. The coverage configuration includes branches and excludes `src/ui/*`; functional UI HTTP-client tests still run, but their module is outside the coverage denominator. `coverage.xml` is generated and ignored by Git. Plain `uv run pytest` runs tests without enforcing coverage; use `make test` for the gate.

Target the new tests:

```bash
uv run --frozen pytest -v \
  tests/test_app_lifecycle.py \
  tests/test_api_network.py \
  tests/test_ingestion_index_integration.py \
  tests/unit/test_ollama_embedder.py \
  tests/unit/test_runtime_boundaries.py
```

Expected: all pass on macOS/Linux without a running model or broker. The real-HTTP test is skipped on Windows because it passes a POSIX listening socket to Uvicorn. It uses a temporary database and an available socket, not ports 8000/8501, so it does not require stopping your local UI.

| Test area | What a pass establishes | What it does not establish |
|---|---|---|
| Embedder batching | Boundary sizes, request count, ordering, error propagation | Real Ollama embedding quality |
| App lifecycle | Startup hook and liveness/schema contract | Dependency readiness |
| Ingestion/index integration | Real SQLite/embedded Chroma/BM25 wiring and idempotency | Queue delivery or model inference |
| Real HTTP | Uvicorn startup, routing, validation, metrics | Browser interaction or a full generated answer |
| Runtime boundaries | Empty/optional LLM fields, fallback, missing jobs, vector-client selection | Infrastructure availability |

### 11c. Native API and UI smoke check — no Docker

If the intended API/UI are already running, use them; do not start duplicates. Otherwise, from the repo root in separate terminals:

```bash
make dev
```

```bash
make ui
```

In a third terminal:

```bash
curl --max-time 5 -fsS http://127.0.0.1:8000/api/live
curl --max-time 5 -fsS http://127.0.0.1:8501/_stcore/health
curl --max-time 5 -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/docs
curl --max-time 5 -fsS http://127.0.0.1:8000/metrics
```

Expected: `{"status":"alive"}`, `ok`, HTTP `200` for `/docs`, and Prometheus text. Open `http://127.0.0.1:8501` in the browser and check for render/import exceptions. A degraded badge is expected if a dependency or BM25 is missing; it is not a UI startup failure.

For real chat, start native Ollama, pull both models (§0d–0e), and seed compatible local indexes (§3a). For queued ingestion, also start Redis and `make worker`. All native processes must use matching configuration. Do not run synchronous seeding while the worker is actively ingesting. Native Ollama generally uses Apple Silicon better than Dockerized Ollama; benchmark on the path you intend to use.

### 11d. Compose validation and image build

Stop only the native API/UI processes you started before launching Compose on ports 8000/8501. Configuration validation itself does not require stopping them.

```bash
compose config --quiet
compose config --services
docker build --tag intelligencehub:phase9-check .
```

Expected: config validation exits 0; default services include `app`, `ui`, `worker`, `ollama`, `models`, `chroma`, and `redis`. The seed service is behind the `tools` profile and is available via `compose --profile tools config --services`. The image build must finish successfully, not merely install system packages.

If the build reports `CERTIFICATE_VERIFY_FAILED` / a self-signed certificate chain during package installation, the container does not trust the network's certificate chain. Obtain the approved corporate CA/build trust configuration. Do not use insecure/trusted-host bypasses or disable verification. Missing buildx is a separate local tooling problem, not a reason to change repository security settings.

A successful config parse is not a successful image build. A successful image build is not a successful full deployment.

### 11e. Start the full stack and inspect prerequisites

```bash
make docker-up
compose ps --all
compose logs --tail=100 models app worker ui chroma redis
```

Expected after initialization:

| Service | Expected state |
|---|---|
| `ollama`, `chroma`, `redis` | Running and healthy |
| `models` | Exited with code 0 after both model pulls |
| `app`, `ui` | Running and healthy |
| `worker` | Running; logs show Celery readiness (no health check configured) |
| `seed` | Not normally running; tool invoked explicitly |

The model initializer requires internet on first use. The API waits for model initialization and Chroma/Redis health. Empty BM25 does not prevent API liveness. Only API/UI ports are published to host loopback; do not expect host connections to container Ollama/Chroma/Redis ports.

```bash
curl --max-time 5 -fsS http://127.0.0.1:8000/api/live
curl --max-time 5 -fsS http://127.0.0.1:8501/_stcore/health
compose exec redis redis-cli ping
compose exec ollama ollama list
```

Expected: liveness JSON, `ok`, `PONG`, and both configured model names. Keep full logs if a model pull or health check fails; do not mark startup complete merely because containers were created.

### 11f. Seeding, queued ingestion, and cited answers

This writes persistent data. Run only when queued ingestion is idle:

```bash
make seed
curl --max-time 15 -fsS http://127.0.0.1:8000/api/health
curl --max-time 15 -fsS http://127.0.0.1:8000/api/stats
```

Expected: all demo sources report `status=done`; health JSON reports `status=ok` with component booleans true; SQLite chunks and Chroma vectors are positive and equal, with `index_drift=0`. `make seed` stops the worker and starts it again using an exit trap; a failed seed still has to be investigated.

For real queue delivery, add a source through the UI using **Markdown** and `/app/corpus/docs`, or submit:

```bash
curl --max-time 15 -fsS -X POST http://127.0.0.1:8000/api/ingest \
  -H 'Content-Type: application/json' \
  -d '{"name":"phase9-queue-smoke","source_type":"markdown","location":"/app/corpus/docs"}'
```

Record `job_id` and `data_source_id`. Submit only once per new source; duplicate POSTs create separate sources. Poll `/api/ingest/{job_id}` until `done` or `failed`. Inspect `error` and worker logs on failure. `queued` / HTTP 202 proves publication only. For subsequent ingestion of the same source, use `POST /api/ingest/sources/{data_source_id}/refresh`.

In the UI, ask a corpus-specific question such as "Why can a Kubernetes pod be evicted?" Expected: an answer supported by the retrieved documents with citation cards showing relevant source paths. Test streaming and non-streaming modes, then repeat §9d–9h. A model may refuse; inspect retrieval/context rather than labeling any answer as success. Health's Ollama probe lists models but does not prove a particular model can generate successfully.

### 11g. Persistence without deleting data

Record `/api/stats` counts and one cited answer after successful ingestion. Then:

```bash
make docker-down
make docker-up
```

Do not run seed again before verifying persistence. Expected: existing sources and positive chunk/vector counts remain; a question answerable before shutdown is still answerable afterward. Generated wording need not be identical. Restarting does not preserve in-memory conversation history or process-local Prometheus counters; those resets do not mean index data was lost.

Named volumes must be retained. Do not use volume-deletion options, delete databases, or remove individual derived indexes as part of this check. Host `data/` and Compose named volumes are separate stores; switching run modes is not a persistence migration.

### 11h. CI and evaluation boundaries

Inspect the CI workflow and, after pushing through your normal workflow, inspect the actual GitHub Actions run. Expected: install → lint → mypy → tests/coverage succeeds, then Compose validation and image build succeed. The coverage artifact should contain `coverage.xml`. No hosted run has been claimed during hardening, and this procedure does not require pushing automatically.

The workflow builds but does not publish or deploy an image. It runs metric/unit tests, not real-model quality benchmarks. For native evaluation with seeded local indexes:

```bash
make eval EVAL_ARGS="--limit 5"
make eval EVAL_ARGS="--e2e --limit 5"
```

Inspect the generated report as described in §10 and [evaluation methodology](evaluation.md). `make eval` does not read Docker's named volumes. Its current PASS/FAIL report criteria do not control the process exit status, so a zero exit is not proof that Recall@10/p95 targets passed. No retrieval/latency numbers are invented for this phase.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `uv`, `ollama`, or `redis-cli`: command not found | Missing installation or PATH | Install the missing tool, reopen the terminal, and check its version |
| `curl` cannot connect to port 11434 | Ollama stopped/wrong address | Start `ollama serve` or the macOS app; verify the configured host/port |
| Ollama says address already in use | Another instance owns port 11434 | Verify the existing server with curl; do not launch a duplicate |
| Model not found | Model was not pulled into this Ollama instance | Run `ollama pull nomic-embed-text` against the same server used by the app |
| `ollama_unavailable_falling_back` | Ollama request failed (server, model, or other error) | Inspect the logged error and run §0e directly; fallback may download a model and produces 384-dim vectors rather than 768 |
| `RuntimeError: Embedding dim mismatch` | Mixed embedders across runs | Restore the original embedder or use fresh SQLite, Chroma, and BM25 paths together; retain existing data |
| HTTP 503 queue unavailable / `Could not publish ingestion task` | Redis unreachable | Start/check Redis and `REDIS_URL`, or use the synchronous seed script without Redis |
| Job remains `queued` | Worker stopped or using a different broker | Check worker readiness, registered task, and matching `REDIS_URL` |
| Job is `failed` | Ingestion or indexing error | Read the status response's `error` and worker logs; validate input path and model availability |
| Worker cannot read a local path | Path exists only on the API host/container | Use an absolute path visible to the worker; the local workflow assumes API and worker share the filesystem |
| Counts differ or both are zero | Wrong storage paths, no ingestion, or index drift | Confirm configuration and job completion; reproduce using fresh isolated paths, not by deleting Chroma alone |
| Empty BM25 query results | Index not loaded or not built | Call `index.load()` (§3d) or `load()` inside `from_defaults()`; check the pickle path matches the configured `BM25_INDEX_PATH` |
| `bm25_index_missing` warning in §6 | No `bm25_index.pkl` at the configured path | Ingest a corpus first (§3a); verify `BM25_INDEX_PATH` matches the storage used during ingestion |
| §6 results but `confident=False` | Weak corpus match or unrelated query | Expected for out-of-domain queries (§6d); for in-domain queries check the corpus covers the topic |
| `query_rewrite_failed` / `rerank_failed_fallback_to_rrf` warnings | Ollama down or LLM output unparseable | By design — retrieval degrades gracefully; restart Ollama to restore rewriting/reranking (§6c) |
| §7 answer has no `[n]` citations | Model ignored the citation format | Inspect the raw answer; strengthen the prompt or accept empty `sources` — content may still be grounded |
| §7 refusal on an in-domain question | Low retrieval confidence (gate 1) or weak context | Check §6a results for the same query; tune `min_confidence_threshold` during Phase 7 eval |
| Follow-up answers don't use prior context | New `session_id` or generator recreated | Use the same `session_id`; construct `RAGGenerator` once per process (§7c) |
| `model 'llama3.2:3b' not found` | Chat model not pulled | `ollama pull llama3.2:3b` against the configured `OLLAMA_BASE_URL` |
| `/api/query` slow on first call | `get_rag()` lazy-builds embedder/BM25/Chroma on first request | Expected one-time cost; later requests reuse the singleton |
| `/api/health` reports `degraded` | One component probe failed | Read the per-component booleans; `health_probe_failed` warnings in API logs name the cause |
| SSE stream arrives all at once | Client buffering | Use `curl -N`; browser `EventSource` streams natively |
| 405 on `GET /api/sources/{id}` | Route only defines DELETE | Expected REST behavior — use `GET /api/sources` to list |
| `index_drift` nonzero in `/api/stats` | Chroma/SQLite out of sync (§3b) | Inspect job errors; re-ingest the source or refresh it |
| Delete returns 204 but BM25 still hits old terms | Rebuild raced a concurrent ingest | Re-run `_rebuild_bm25` via another delete/ingest, or rebuild from SQLite per §3d |
| Uvicorn address already in use | Another process owns port 8000 | Use the existing intended API or choose `--port 8001` and update curl URLs |
| SQLite database is locked | Concurrent writers | Run smoke ingestion jobs sequentially and avoid simultaneous seed/API writes |
| `ModuleNotFoundError: No module named 'src'` when starting Streamlit | Not running inside the project environment | Run `uv run streamlit run src/ui/app.py` from the repo root (`uv sync` installs `src` as a package) |
| Sidebar badge red but API is up | Wrong API URL or stale 15 s health cache | Check Settings → API base URL; click **Test connection** (clears the cache) |
| UI job stuck at `pending` | Worker not running / different broker | Start the worker (§5b); verify `REDIS_URL` matches the API |
| UI job `failed` with "Not a file"/"Not a directory" | Path not visible to the worker | Use an absolute path on the worker's machine; in Docker use `/app/corpus/...` |
| Chat answer streams but no citation cards | Model emitted no `[n]` markers, or API is pre-Phase-7 | Check §8d shows an `event: sources`; restart the API after updating the code |
| Filter returns fewer/odd results, citations show `docN-chunkM` | Chunks ingested before the Phase 7 metadata fix | Delete and re-add the source (§9c-10, §9c-3); "Re-ingest" skips unchanged files |
| New source not found by chat until API restart | Native Chroma `PersistentClient` multi-process staleness | Restart the native API or use the Phase 9 Compose Chroma server; if already server-backed, inspect ingestion and matching configuration |
| Docker build fails with `CERTIFICATE_VERIFY_FAILED` | Build container does not trust the corporate certificate chain | Obtain approved CA/build trust configuration; do not disable TLS verification |
| `docker: unknown command: docker compose` | Compose plugin absent | Use the installed standalone `docker-compose`; Makefile auto-detects it |
| Compose fails to bind 8000/8501 | Native API/UI or another deployment owns the port | Stop only your intended conflicting process or explicitly configure different ports |
| API live, chat unavailable | Liveness only checks the HTTP process | Check diagnostic health, model availability, seeded indexes, and the query error |
| Model initializer exited | One-shot initializer completed or failed | Exit code 0 is expected; nonzero requires inspecting `models` logs |
| Settings/filter reset when switching pages | `init_state()` not called or key missing from `_WIDGET_KEYS` | Ensure `app.py` calls `init_state()` before rendering pages |
| `run_benchmark` exits `parser.error: No BM25 index on disk` | No persisted index at `BM25_INDEX_PATH` | Ingest via §3a with matching storage exports |
| Report `embedder: SentenceTransformerEmbedder` | Ollama was down during the run | Restart Ollama and rerun — 384-dim vectors are incompatible with a 768-dim index |
| `Embedding dim mismatch` during benchmark | Index built with a different model | Re-ingest with the configured `EMBEDDING_MODEL`, or use fresh isolated storage |
| BM25 recall ~0, dense fine | Chunks lack `source_path` in `chunk_metadata` (pre-Phase-7 data) | Force re-ingest every source (§5d `?force=true`) |
| Golden item never matches | `path`/`contains` substring doesn't appear in any chunk's `source_path` or text | Inspect `top3` in `results.json` (§10b); widen `path` or fix `contains` to match actual chunk text |
| `--e2e` extremely slow | Judge + generation LLM calls per question on CPU | Use `--limit`, or expect tens of minutes; stream speed in §8d is a sanity check |
| Faithfulness `None` on many items | Judge output unparseable or answer refused | Refusals are ungraded by design; otherwise retry or use a stronger `--judge-model` |
| `ModuleNotFoundError: evaluation` running benchmark | Invoked as a script file instead of module | Run `uv run python -m evaluation.benchmarks.run_benchmark` from the repo root |

## 12. Stop services after testing

- Press `Ctrl+C` in the worker and Uvicorn terminals; allow active work to finish before closing them.
- Press `Ctrl+C` in a foreground `ollama serve` or `redis-server` terminal. If using the Ollama app, quit it when no longer needed.
- If you started Redis with Homebrew specifically for this test, use `brew services stop redis`.
- If you started only the Compose Redis service, use `docker compose stop redis`.
- Leave shared/pre-existing services running if other applications need them.

Stopping services does not delete models or test data. Do not remove SQLite, Chroma, or BM25 independently: unchanged-file deduplication means simply rerunning ingestion may not reconstruct a deleted index. For another clean test, select a new isolated set of storage paths in §0c.

## 13. Completion checklist

- [ ] Dependency installation completes without errors.
- [ ] Ruff, mypy, and pytest results are recorded; failures are investigated rather than ignored.
- [ ] Direct Ollama embedding check returns one 768-dimensional vector with the default model.
- [ ] Each seeded source reports `status=done`.
- [ ] SQLite and Chroma counts match and are greater than zero.
- [ ] Semantic results are relevant and BM25 keyword check passes.
- [ ] An unchanged second seed run adds no duplicate chunks/vectors.
- [ ] If testing the API: health returns 200, ingestion returns 202, and polling reaches `done` with no error.
- [ ] Retrieval pipeline returns results with `confident=True` on an in-domain query (§6a).
- [ ] `source_type` filter leaks no wrong-type chunks (§6b).
- [ ] Retrieval still returns results with Ollama stopped — fallback warnings logged, no crash (§6c).
- [ ] Out-of-domain query produces `confident=False` (§6d).
- [ ] In-domain query returns a cited answer with source paths (§7a).
- [ ] Out-of-domain query returns the refusal with `refused=True`, empty sources (§7b).
- [ ] Follow-up question resolves via session memory (§7c).
- [ ] `/api/health` returns per-component status; `/docs` shows all routes (§8a).
- [ ] `POST /api/query` returns cited JSON; empty query returns 422 (§8b–8c).
- [ ] SSE stream emits JSON `token` events, then `sources`, then `done` with a real confidence label (§8d).
- [ ] `/api/stats` reports `index_drift=0`; `/metrics` exposes request counters (§8e).
- [ ] Headless `AppTest` renders the UI with no exceptions (§9a).
- [ ] Sidebar health badge reflects ok / degraded / unreachable (§9b).
- [ ] A source added in the UI reaches `done` with live progress, and appears in the table with `document_count > 0` (§9c).
- [ ] Failed path and Redis-down cases show clear errors; delete requires confirmation and keeps `index_drift=0` (§9c).
- [ ] Chat streams tokens, shows a confidence badge and `[n] path` citation cards with snippets and RRF scores (§9d).
- [ ] Follow-up uses memory; "New conversation" clears it; refusal shows the grey badge (§9d).
- [ ] Non-streaming mode returns the same answer shape (§9d-8).
- [ ] Source-type filter restricts citations, persists across pages, and BM25 hits survive filtering (§9e).
- [ ] A newly ingested source is answerable without restarting the API (§9f).
- [ ] Analytics shows drift 0, server request counts, and session latency/p95/confidence charts (§9g).
- [ ] Settings URL/timeout/streaming changes take effect and persist across pages (§9h).
- [ ] Eval metric tests pass (§10a).
- [ ] Retrieval benchmark completes for all three strategies with `n` = dataset size and `embedder: OllamaEmbedder` (§10b).
- [ ] Hybrid Recall@10 and NDCG@10 ≥ dense and BM25 legs (§10b).
- [ ] Report shows PASS/FAIL verdicts for both acceptance criteria; misses inspected via `top3` in `results.json` (§10b–10d).
- [ ] `--e2e` report includes faithfulness, refusal rate, and p50/p90/p95 end-to-end latency (§10c).
- [ ] `make check` passes and combined backend coverage is at least 80% (§11b).
- [ ] Lifecycle, real-HTTP, indexing integration, batching, and runtime-boundary tests pass (§11b).
- [ ] Native `/api/live`, Streamlit health, browser render, `/docs`, and `/metrics` are checked (§11c).
- [ ] Compose config and actual image build succeed; certificate/tooling failures are recorded separately (§11d).
- [ ] Models initialize successfully and expected long-lived containers run (§11e).
- [ ] Docker seed, real queued ingestion, and cited UI answers succeed (§11f).
- [ ] Index data survives shutdown/startup without reseeding or volume deletion (§11g).
- [ ] Actual hosted CI result is inspected; no deployment or benchmark success inferred from workflow existence (§11h).
- [ ] Services started solely for testing are stopped when finished.
