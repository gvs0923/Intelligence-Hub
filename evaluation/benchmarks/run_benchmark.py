import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from evaluation.evaluator import (
    DATASET,
    FaithfulnessJudge,
    evaluate_generation,
    evaluate_retrieval,
    load_golden,
    render_report,
    summarize,
)
from src.config import get_settings
from src.generation.generator import RAGGenerator
from src.generation.llm_client import LLMClient
from src.indexing.bm25 import BM25Index
from src.indexing.embedders import get_embedder
from src.indexing.vector_store import VectorStore
from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.dense import DenseRetriever
from src.retrieval.pipeline import RetrievalPipeline

REPORTS = Path(__file__).resolve().parents[1] / "reports"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the golden-set evaluation")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--e2e", action="store_true", help="Also run generation + LLM-as-judge (slow)")
    parser.add_argument("--judge-model", default=None, help="Defaults to LLM_MODEL")
    parser.add_argument("--limit", type=int, default=None, help="Only the first N questions")
    args = parser.parse_args()

    items = load_golden(args.dataset)[: args.limit]

    embedder = get_embedder()
    bm25_index = BM25Index()
    if not bm25_index.load():
        parser.error("No BM25 index on disk. Ingest the corpus first.")
    dense = DenseRetriever(embedder, VectorStore())
    bm25 = BM25Retriever(bm25_index)
    hybrid = RetrievalPipeline(dense, bm25)

    strategies = {
        "dense": dense.retrieve,
        "bm25": bm25.retrieve,
        "hybrid": lambda q, k: hybrid.retrieve(q, top_k=k)[0],
    }
    retrieval_rows = evaluate_retrieval(items, strategies)

    generation_rows: list[dict] = []
    judge = FaithfulnessJudge(args.judge_model)
    if args.e2e:
        rag = RAGGenerator(RetrievalPipeline.from_defaults(), LLMClient())
        generation_rows = evaluate_generation(items, rag, judge)

    settings = get_settings()
    meta = {
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "questions": len(items),
        "embedder": type(embedder).__name__,
        "llm": settings.llm_model,
        "judge": judge.model if args.e2e else "-",
        "rrf_k": settings.rrf_k,
    }
    out = REPORTS / datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    (out / "results.json").write_text(json.dumps(
        {"meta": meta, "retrieval": retrieval_rows, "generation": generation_rows}, indent=2
    ))
    report = render_report(summarize(retrieval_rows), summarize(generation_rows), meta)
    (out / "report.md").write_text(report)
    print(report)
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()