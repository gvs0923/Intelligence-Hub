# Deployment and verification

## Prerequisites

Use Docker with Compose v2 or newer, Git, and network access for initial dependency/model downloads and Git ingestion. Allow multiple GB of disk and RAM for Python ML dependencies and model storage. Hardware determines inference latency; do not promise the plan's p95 target without benchmarking.

`make` automatically uses `docker compose` when the plugin exists, otherwise `docker-compose`. Override with `make COMPOSE="docker-compose" docker-up` if needed. The Docker image uses uv 0.12.23 to match the current lockfile generation. A working buildx plugin is recommended for image builds.

## Native startup without Docker

Use this path to inspect the UI without building containers. From the repository root:

```bash
make setup
make dev
```

In a separate terminal, run `make ui`. Open `http://127.0.0.1:8501`; API docs are at `http://127.0.0.1:8000/docs`. These processes can start without an available model, but chat will not work until compatible models/indexes are ready. Reuse existing intended processes rather than launching duplicate listeners.

For real chat, start the Ollama app or `ollama serve`, then:

```bash
ollama pull nomic-embed-text
ollama pull llama3.2:3b
uv run --frozen python -m scripts.seed_demo_data \
  --docs corpus/docs --incidents corpus/incidents.json \
  --repo https://github.com/nolar/kopf --code corpus/java
```

This synchronous seed writes the configured local stores and needs no Redis/worker. Do not run it concurrently with ingestion. Keep settings and working directory consistent across terminals. If you want queued ingestion through the UI, start Redis using your normal local installation and run `make worker` in another terminal. Native Chroma is embedded unless `CHROMA_HOST` is explicitly configured.

Stop native API/UI listeners before testing Docker on the same ports. Prefer native Ollama for Apple Silicon acceleration; this guide does not claim equivalent Docker GPU performance.

## Docker startup

From the repository root:

```bash
[ -f .env ] || cp .env.example .env
make docker-up
```

Equivalent Compose command: `docker compose up --build -d` (or use the standalone `docker-compose` executable). Inspect `docker compose ps` and `docker compose logs models app worker ui chroma` if startup fails. The model initializer exits successfully; it is not expected to remain running.

Application/image variables can be supplied through the shell or `.env`, except native `API_URL`, which the UI reads from its process environment:

| Variable | Default / purpose |
|---|---|
| `OLLAMA_IMAGE` | `ollama/ollama:0.12.6` |
| `CHROMA_IMAGE` | `chromadb/chroma:1.5.9`, matching the locked Python client |
| `REDIS_IMAGE` | A pinned Redis digest in Compose |
| `LLM_MODEL` | `llama3.2:3b` |
| `EMBEDDING_MODEL` | `nomic-embed-text`; changing dimensions requires a compatible fresh index |
| `BM25_INDEX_PATH` | Native default `./data/bm25_index.pkl`; Compose sets `/app/data/bm25_index.pkl` |
| `CHROMA_HOST` | Native default unset/embedded; Compose overrides to `chroma` |
| `CHROMA_PORT` | `8000` within the container network |
| `API_URL` | Native UI process environment, e.g. `API_URL=http://127.0.0.1:8000 make ui`; Compose explicitly sets `http://app:8000` |

Pydantic ignores unrelated dotenv keys so Compose-only image settings can coexist with application settings. Do not commit a real `.env`. Infrastructure images are versioned starting points, not a claim of a completed security audit; pin reviewed digests for release use.

## Seed demo data

Wait for the API to be live, and run when no ingestion job is active:

```bash
make seed
```

This stops the worker, runs the existing seed script against `corpus/docs`, `corpus/incidents.json`, `corpus/java`, and the public Git repository, then starts the worker again. Failure remains a nonzero exit code. `corpus/` is mounted read-only. Use `/app/corpus/...` paths when submitting filesystem ingestion through the Docker UI/API; host paths are not container paths.

Do not run a second seed process at the same time. The script reuses sources and skips unchanged documents, but this is not a general index-repair mechanism. Refresh with `force=true` when existing documents need reindexing, after investigating drift and ensuring backups.

## Verify HTTP and indexes

```bash
curl -fsS http://localhost:8000/api/live
curl -fsS http://localhost:8000/api/health
curl -fsS http://localhost:8000/api/stats
curl -fsS http://localhost:8000/metrics
```

Liveness returns `{"status":"alive"}`. After successful seeding, inspect the health JSON for `status=ok`, and stats for positive counts and zero `index_drift`. Health HTTP 200 alone does not prove readiness. Open `http://localhost:8501` for the UI and `http://localhost:8000/docs` for API contracts.

A full manual ingestion smoke test is:

```bash
curl -fsS -X POST http://localhost:8000/api/ingest \
  -H 'Content-Type: application/json' \
  -d '{"name":"smoke-docs","source_type":"markdown","location":"/app/corpus/docs"}'
```

Poll `/api/ingest/{job_id}` using the returned ID until `done` or `failed`. `queued` is not success. Query for corpus-specific information and inspect citations. Restart the same deployment without deleting volumes and repeat to check persistence. Submit this POST once per new source; use the refresh route for repeat ingestion of that source.

## Tests and evaluation

```bash
make setup
make check
make eval EVAL_ARGS="--limit 5"
make eval EVAL_ARGS="--e2e --limit 5"
```

Quality checks require no running model. Test storage is redirected to a temporary directory before application imports. Coverage enforces 80% backend line-and-branch coverage. Streamlit rendering is excluded; API-client tests still run. The real-HTTP smoke test starts Uvicorn on an isolated socket and checks startup, routes, validation, and metrics; it does not claim to test model quality or Celery delivery.

Evaluation uses native/local configured indexes, not Compose volumes. Seed a local corpus with the same script/settings before using `make eval`. See [evaluation methodology](evaluation.md).

## Persistence, shutdown, and recovery

```bash
make docker-down
```

This retains named volumes. Do not use volume-deletion options to fix startup failures. Stop all ingestion and back up SQLite, BM25, Chroma storage, and relevant model/config information together before upgrades. SQLite and Chroma format changes may require an explicit migration or re-ingestion. A new server-backed Compose deployment does not consume old host `data/` automatically.

For macOS performance, native Ollama can use Metal while Linux containers generally cannot. Run the whole native development path if that matters; simply changing a host `.env` URL will not override Compose's explicit internal Ollama URL.

This deployment has no authentication, TLS termination, or multi-tenant controls. Keep it local/trusted. CI does not publish images or perform production deployment.
