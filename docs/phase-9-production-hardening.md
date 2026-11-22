# Phase 9 — Production Hardening

**Goal:** make the existing local RAG system deployable, testable, and documented without claiming an unverified production release.

Phases 1–8 supply ingestion, indexing, hybrid retrieval, cited generation, HTTP APIs, Streamlit, and evaluation. This phase packages and checks those components; it does not replace the retrieval algorithm or invent benchmark results.

---

## What was built

| Area | Files | What changed |
|---|---|---|
| Container image | `Dockerfile`, `.dockerignore` | Frozen two-stage dependency/project installation, pinned uv, non-root runtime, correct application/script copies, liveness health check, build-context exclusions |
| Stack orchestration | `docker-compose.yml` | API, Streamlit, solo Celery worker, Ollama, model initialization, Chroma server, Redis, optional seed service, named volumes, localhost-only published ports |
| Commands | `Makefile` | Setup, native API/UI/worker, lint, typecheck, coverage tests, full quality check, Compose startup/shutdown/seeding, real Phase 8 evaluation module |
| Automation | `.github/workflows/ci.yml` | Lint, mypy, pytest/coverage, coverage artifact, Compose validation, Docker image build |
| Health | `src/api/main.py` | `/api/live` endpoint independent of models/index readiness |
| Quality gates | `pyproject.toml`, `uv.lock` | pytest-cov, branch measurement, backend coverage threshold 80%, mypy configuration |
| Runtime boundaries | Logging, LLM, indexing, registry, stats, task modules | Correct library types, optional model output handling, safe missing-job error, metadata guard, precise scalar-count typing |
| Test safety | `tests/conftest.py` | Temporary test storage before application imports; no use of normal developer indexes |
| Documentation | README, architecture, deployment, evaluation, this file, testing manual | Actual commands, code paths, topology, limitations, verification procedure, and recorded evidence |

New/follow-up tests:

- `tests/unit/test_ollama_embedder.py`: 0/1/32/33/65 inputs, batching order and request sizes, propagated embedding failures.
- `tests/test_app_lifecycle.py`: context-managed TestClient runs startup, initializes the database, and exposes liveness/schema.
- `tests/test_ingestion_index_integration.py`: Markdown → chunking → SQLite → real embedded Chroma → persisted BM25; unchanged re-ingestion remains idempotent with a deterministic fake embedder.
- `tests/test_api_network.py`: a real Uvicorn subprocess on an inherited isolated socket; HTTP liveness, schema, source listing, invalid ingestion request, metrics, and process cleanup.
- `tests/unit/test_runtime_boundaries.py`: nullable model content, empty stream chunks, rewrite/rerank fallback, missing task job/session cleanup, HTTP-client selection, and absent Chroma metadata.

## Architecture: what changed and what did not

See [the architecture diagram and decisions](architecture.md).

The vector wrapper already had two modes. Compose now supplies `CHROMA_HOST=chroma` and `CHROMA_PORT=8000`, selecting `HttpClient` so independent API/worker processes share a Chroma server. Native execution still selects `PersistentClient` when no host is configured. Explicit persistence paths take precedence for embedded test stores.

SQLite remains the source of truth for text and metadata. Chroma holds vectors; BM25 holds a derived keyword index. The API and worker share SQLite/BM25 through `app_data`; Chroma, Ollama, and Redis use separate volumes. There is no automatic migration of host `data/` into Docker volumes.

Streamlit already exists at `src/ui/app.py`, and the benchmark already exists at `evaluation/benchmarks/run_benchmark.py`. The earlier assessment that those phases were missing was incorrect. Compose and `make eval` now use their actual entrypoints.

## Important code decisions — what, why, how

### 1. Build dependencies before installing the project

The Dockerfile first copies `pyproject.toml` and `uv.lock`, then runs `uv sync --frozen --no-dev --no-install-project`. This caches third-party dependencies without trying to build a package whose source is not there yet. After copying README, source, and scripts, another frozen sync installs the application non-editably.

**Lesson:** dependency caching is only useful if package build requirements are respected. Frozen installs prevent unreviewed dependency resolution during image builds. The runtime starts the installed `uvicorn` directly instead of syncing packages at startup.

### 2. Liveness is not readiness

`/api/live` reports the HTTP process is alive. `/api/health` remains the diagnostic dependency endpoint and may report `degraded` in an HTTP 200 body. BM25 is absent on a fresh installation, so making startup depend on a seeded index would block the very worker needed to build it.

**Lesson:** separate process availability, dependency readiness, and corpus readiness. A 200 response from diagnostic health is not proof of query readiness.

### 3. One-shot models, long-lived worker

Ollama first becomes reachable; a one-shot service pulls the chat and embedding models; API startup then proceeds. Redis being alive does not execute jobs: the separate Celery worker does that. The UI sends HTTP requests to `http://app:8000` inside Docker rather than its own localhost.

**Lesson:** service ordering must express operational prerequisites, not just container creation order.

### 4. One ingestion writer

The worker uses `--pool=solo --concurrency=1`. `make seed` stops it, runs the synchronous seed service, and uses a shell trap to start it again even if seeding fails. Run this only when active ingestion is idle. Do not run concurrent seeds, scale worker replicas, or delete sources while another writer is changing the indexes.

**Lesson:** a queue does not make shared file-based indexes safe for arbitrary concurrency. Chroma server mode does not remove SQLite/BM25 writer constraints.

### 5. Optional external output is a real runtime case

Ollama response content can be `None`. One-shot chat normalizes that to an empty string; streaming skips missing/empty chunks. Query rewriting retains the original query when output is empty; malformed reranking falls back to the existing RRF order. Embedding sequences are converted to the project's concrete list representation.

**Lesson:** type errors can reveal real integration boundaries. Fix the representation/behavior and test it rather than disabling the checker.

### 6. Tests have different responsibilities

Deterministic fakes remove model/network variability from automated tests. Embedded Chroma and SQLite still exercise real storage integration. A separate real-HTTP test verifies Uvicorn startup and HTTP contracts. The actual model, broker delivery, UI chat interaction, and container persistence still need smoke tests.

Coverage measures statements and branches in `src`, excluding `src/ui/*`; UI-client functional tests still run. The 80% gate is not an assertion that every subsystem has 80% coverage or that browser rendering is tested.

**Lesson:** report test scope alongside its percentage. Passing mocks cannot establish real-model quality.

### 7. CI builds but does not deploy

GitHub Actions runs the same Makefile gates as local development, retains coverage XML, validates Compose, and builds an image after quality checks pass. It has read-only repository permissions. It does not publish images, pull inference models, seed a production database, run a real-model benchmark, or deploy.

**Lesson:** an automated image build is CI, not a complete delivery pipeline. Registry promotion, deployment credentials, immutable release pinning, and a target environment are separate decisions.

## How to run

Native UI inspection without Docker:

```bash
make setup
make dev
```

Run `make ui` in another terminal. Chat requires Ollama with the configured embedding/chat models and seeded compatible indexes. Queued ingestion additionally needs Redis and `make worker`. Synchronous native seeding does not need Redis or a worker; see the [deployment guide](deployment.md).

Container startup and seeding:

```bash
make docker-up
make seed
```

Do not run native and Docker API/UI instances on the same host ports. `make` supports both the Compose plugin and standalone `docker-compose`. First-time model pulls require internet. Native Ollama generally performs better on Apple Silicon because Docker's Linux environment does not provide equivalent Metal access.

## Recorded verification — not benchmark claims

The implementation session captured the following local results:

| Check | Recorded result | Scope |
|---|---|---|
| Ruff | Passed | `src`, `tests`, `scripts`, `evaluation` |
| mypy | Passed, 74 source files | `src` |
| pytest | 85 passed | Existing suite plus hardening tests |
| Combined statement/branch coverage | 86.80%, threshold 80% | Backend; `src/ui/*` excluded |
| Compose configuration | Validated with standalone `docker-compose config --quiet` | Syntax/configuration only |
| Native API/UI startup | `/api/live` returned `{"status":"alive"}`; Streamlit `/_stcore/health` returned `ok` | Process/HTTP availability, not a complete browser workflow |
| Docker image build | Blocked at `pip install uv` by `CERTIFICATE_VERIFY_FAILED` / self-signed certificate chain | No successful image or full-stack run claimed |
| Real-model evaluation | Not run during Phase 9 hardening | No Recall/MRR/NDCG/faithfulness/p95 numbers claimed |
| Hosted GitHub Actions run | Not observed | Workflow definition exists; no green hosted run claimed |

These are historical observations, not guaranteed output of every future run. The user is handling full-stack Docker testing. Supply the approved organizational CA/trust configuration for the build environment before retrying a certificate-blocked build; do not disable TLS verification. Editing `.env.example` was blocked by organization policy; optional settings are documented in `deployment.md` instead.

## Acceptance checklist and remaining work

- [x] Implementation of Compose services, model initialization, and seed path.
- [x] Backend coverage gate, integration checks, and real-HTTP API smoke test.
- [x] CI workflow definition, Makefile, README and separate architecture/evaluation/deployment docs.
- [x] Local lint, typecheck, tests, coverage, and Compose configuration verified.
- [ ] Successful clean image build and full-stack startup on the target machine.
- [ ] Real queued ingestion reaches `done`, with relevant cited answers through the UI.
- [ ] Restart preserves indexes and makes the same source queryable.
- [ ] Hosted CI run passes.
- [ ] Target-hardware benchmark report collected and acceptance criteria inspected.

The plan's retrieval/latency targets remain measurements to make, not facts established by hardening. Follow [Testing §11](TESTING.md#11-phase-9--production-hardening) for repeatable checks. Phase 9 implementation is present; do not mark deployment acceptance complete while its verification items remain unchecked.
