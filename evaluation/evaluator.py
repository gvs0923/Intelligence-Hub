import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import ollama
from pydantic import BaseModel, Field

from evaluation.metrics import mean, ndcg_at_k, percentile, recall_at_k, reciprocal_rank
from src.config import get_settings
from src.generation.generator import RAGGenerator
from src.retrieval.base import RetrievalResult

DATASET = Path(__file__).parent / "datasets" / "golden_qa.json"

Retrieve = Callable[[str, int], list[RetrievalResult]]


class Target(BaseModel):
    path: str
    contains: str | None = None
    grade: int = Field(default=2, ge=1, le=3)

    def matches(self, r: RetrievalResult) -> bool:
        if self.path not in r.metadata.get("source_path", ""):
            return False
        return self.contains is None or self.contains.lower() in r.content.lower()


class GoldenItem(BaseModel):
    id: str
    question: str
    targets: list[Target] = Field(min_length=1)


def load_golden(path: Path = DATASET) -> list[GoldenItem]:
    items = [GoldenItem.model_validate(raw) for raw in json.loads(path.read_text())]
    dupes = [i for i, n in Counter(item.id for item in items).items() if n > 1]
    if dupes:
        raise ValueError(f"Duplicate golden ids: {dupes}")
    return items


def evaluate_retrieval(
    items: list[GoldenItem], strategies: dict[str, Retrieve], depth: int = 10
) -> list[dict]:
    rows = []
    for name, retrieve in strategies.items():
        for item in items:
            start = perf_counter()
            ranked = retrieve(item.question, depth)
            latency = perf_counter() - start
            matches = [{t for t, target in enumerate(item.targets) if target.matches(r)} for r in ranked]
            grades = [t.grade for t in item.targets]
            rows.append({
                "strategy": name,
                "id": item.id,
                "latency_s": latency,
                "recall@5": recall_at_k(matches, len(grades), 5),
                "recall@10": recall_at_k(matches, len(grades), 10),
                "mrr": reciprocal_rank(matches),
                "ndcg@10": ndcg_at_k(matches, grades, 10),
                "top3": [r.metadata.get("source_path", "?") for r in ranked[:3]],
            })
    return rows


_JUDGE_PROMPT = """You are checking whether an answer is supported by its sources.

Sources:
{sources}

Question: {question}

Answer:
{answer}

Split the answer into individual factual claims. For each claim decide whether
the sources above directly support it. Ignore citation markers like [1].
Respond with ONLY JSON: {{"claims": [{{"claim": "...", "supported": true}}]}}"""


class FaithfulnessJudge:
    """LLM-as-judge: fraction of the answer's claims supported by the sources it cited."""

    def __init__(self, model: str | None = None):
        settings = get_settings()
        self.model = model or settings.llm_model
        self._client = ollama.Client(host=settings.ollama_base_url)

    def score(self, question: str, answer: str, sources: list[str]) -> float | None:
        if not sources:
            return 0.0
        prompt = _JUDGE_PROMPT.format(sources="\n\n".join(sources), question=question, answer=answer)
        resp = self._client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            format="json",
            options={"temperature": 0},
        )
        try:
            content = resp.message.content or ""
            claims = [c for c in json.loads(content)["claims"] if isinstance(c, dict)]
        except (ValueError, KeyError, TypeError):
            return None
        if not claims:
            return None
        return sum(bool(c.get("supported")) for c in claims) / len(claims)


def evaluate_generation(
    items: list[GoldenItem], rag: RAGGenerator, judge: FaithfulnessJudge
) -> list[dict]:
    rows = []
    for item in items:
        start = perf_counter()
        resp = rag.ask(item.question, session_id=f"eval-{uuid4().hex}")
        latency = perf_counter() - start
        faithfulness = None if resp.refused else judge.score(
            item.question, resp.answer, [f"[{s.index}] {s.text}" for s in resp.sources]
        )
        rows.append({
            "strategy": "end-to-end",
            "id": item.id,
            "latency_s": latency,
            "refused": resp.refused,
            "faithfulness": faithfulness,
        })
    return rows


def summarize(rows: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["strategy"], []).append(row)
    out = []
    for name, group in groups.items():
        latencies = [r["latency_s"] for r in group]
        summary = {"strategy": name, "n": len(group)}
        for metric in ("recall@5", "recall@10", "mrr", "ndcg@10", "faithfulness", "refused"):
            values = [r[metric] for r in group if r.get(metric) is not None]
            if values:
                summary[metric] = mean(values)
        summary |= {
            "p50_s": percentile(latencies, 50),
            "p90_s": percentile(latencies, 90),
            "p95_s": percentile(latencies, 95),
        }
        out.append(summary)
    return out


def render_report(retrieval: list[dict], generation: list[dict], meta: dict) -> str:
    lines = [
        "# Evaluation report", "",
        *[f"- {k}: {v}" for k, v in meta.items()], "",
        "## Retrieval: dense vs BM25 vs hybrid (RRF)", "",
        _table(retrieval, ["strategy", "n", "recall@5", "recall@10", "mrr", "ndcg@10", "p50_s", "p90_s", "p95_s"]),
        "", "### Recall@10", "", "```",
        *[f"{r['strategy']:<12} {'#' * round(r['recall@10'] * 40):<40} {r['recall@10']:.2f}" for r in retrieval],
        "```", "",
    ]
    if generation:
        lines += [
            "## End-to-end (rewrite + hybrid + rerank + generation)", "",
            _table(generation, ["strategy", "n", "faithfulness", "refused", "p50_s", "p90_s", "p95_s"]), "",
        ]
    lines += ["## Acceptance criteria", ""]
    hybrid = next((r for r in retrieval if r["strategy"] == "hybrid"), None)
    if hybrid:
        ok = hybrid["recall@10"] > 0.8
        lines.append(f"- Retrieval Recall@10 > 80% (hybrid): {hybrid['recall@10']:.1%} — {'PASS' if ok else 'FAIL'}")
    if generation:
        ok = generation[0]["p95_s"] < 5
        lines.append(f"- Query latency p95 < 5 s: {generation[0]['p95_s']:.2f} s — {'PASS' if ok else 'FAIL'}")
    return "\n".join(lines) + "\n"


def _table(rows: list[dict], cols: list[str]) -> str:
    def fmt(v):
        return "-" if v is None else f"{v:.3f}" if isinstance(v, float) else str(v)
    return "\n".join([
        "| " + " | ".join(cols) + " |",
        "|" + "---|" * len(cols),
        *["| " + " | ".join(fmt(r.get(c)) for c in cols) + " |" for r in rows],
    ])