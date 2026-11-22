# Evaluation methodology

## Verification status

The evaluator and golden dataset are implemented. Phase 9 verified local automated tests, including the metric tests, but did not run a real-model benchmark or establish Recall@10, faithfulness, or p95 results. The 85-test/86.80%-coverage observation in the phase notes is a software-test result, not an evaluation score. Populate results only from a captured report on the intended corpus and hardware.

## Reproducible inputs

The existing Phase 8 runner is `evaluation.benchmarks.run_benchmark`; `make eval` invokes it as a module. Its default dataset is `evaluation/datasets/golden_qa.json`. Each item has a question, a unique ID, and one or more expected targets with a source-path substring, optional chunk-content substring, and relevance grade from 1 to 3.

Before evaluating, ingest the matching corpus with the same settings/storage paths and embedding model. Confirm Chroma/SQLite counts and BM25 availability. Old chunks without `source_path` metadata can unfairly penalize BM25; inspect metadata or reindex deliberately. Do not infer retrieval quality from unseeded or incompatible indexes.

```bash
make eval
make eval EVAL_ARGS="--limit 5"
make eval EVAL_ARGS="--e2e --limit 5"
make eval EVAL_ARGS="--e2e --judge-model mistral:7b"
```

The judge model must already be available in Ollama. Native `make eval` reads local indexes and cannot automatically see Docker volumes. The seed script accepts `--docs`, `--incidents`, `--repo`, and optional `--code`; run it with the corpus paths used by the golden dataset.

## Retrieval comparison

The runner compares dense-only, BM25-only, and hybrid RRF using the same questions and depth 10. The hybrid comparison omits rewriting/reranking to isolate the fusion strategy.

- Recall@5 and Recall@10 measure the fraction of expected targets retrieved. For single-target questions this is hit rate; multi-target questions earn partial credit.
- MRR averages the reciprocal rank of the first relevant result.
- NDCG@10 rewards higher-graded results near the top and credits each target only once.
- Latency p50/p90/p95 measures per-query retrieval time, not application startup or model download time.

Path/content targets remain useful when vector IDs change across ingestions, but substring matching is a labeling approximation. Review false positives/negatives and maintain the dataset as the corpus changes.

## End-to-end generation

`--e2e` additionally runs the production RAG configuration, including rewriting/reranking and generation. Each question uses a fresh conversation ID to avoid history leakage. An Ollama judge checks factual claims against cited source text. Report faithfulness alongside refusal rate: refusing everything must not appear to be a useful perfect system.

A refused answer or unparseable judge result has no faithfulness score; unsupported judged claims reduce the score. The default judge is the generation model, introducing self-evaluation bias. Prefer an independent, validated judge and human spot checks. Cold model loads, warm caches, CPU/GPU resources, model versions, and corpus size affect latency and should accompany results.

## Reports and acceptance

Each run writes `results.json` and `report.md` under `evaluation/reports/<timestamp>/`, recording configuration metadata and per-question results. Generated reports are ignored by Git by default. Select and review benchmark artifacts explicitly when publishing measured results.

The report checks hybrid Recall@10 > 80% and, with `--e2e`, p95 query latency < 5 seconds. The current runner prints PASS/FAIL but does not turn a failed benchmark criterion into a nonzero process exit. Do not treat its exit code as a quality gate. No benchmark result is claimed by the hardening changes: run on the target deployment and inspect the report.
