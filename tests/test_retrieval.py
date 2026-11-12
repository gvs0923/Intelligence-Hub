
from src.retrieval.base import RetrievalResult
from src.retrieval.confidence import is_confident, retrieval_confidence
from src.retrieval.filters import RetrievalFilters
from src.retrieval.fusion import reciprocal_rank_fusion


def _r(vid: str, score: float, **meta) -> RetrievalResult:
    return RetrievalResult(content=f"text-{vid}", score=score, metadata={"vector_id": vid, **meta})


def test_rrf_boosts_docs_seen_by_both():
    dense = [_r("a", 0.9), _r("b", 0.8), _r("c", 0.7)]
    bm25 = [_r("b", 12.0), _r("d", 9.0), _r("a", 4.0)]
    fused = reciprocal_rank_fusion([dense, bm25], k=60)
    # "b" is #2 dense and #1 bm25 → highest fused score
    assert fused[0].metadata["vector_id"] == "b"
    # every result carries an RRF score, not the raw score
    assert all(r.score < 0.1 for r in fused)


def test_rrf_handles_empty_list():
    fused = reciprocal_rank_fusion([[], [_r("x", 1.0)]], k=60)
    assert [r.metadata["vector_id"] for r in fused] == ["x"]


def test_chroma_where_single_and_multi():
    f = RetrievalFilters(source_type="incident")
    assert f.to_chroma_where() == {"source_type": "incident"}

    f = RetrievalFilters(source_type="incident", severity="P1")
    assert f.to_chroma_where() == {
        "$and": [{"source_type": "incident"}, {"severity": "P1"}]
    }
    assert RetrievalFilters().to_chroma_where() is None


def test_post_filter_matches():
    f = RetrievalFilters(language="python")
    assert f.matches(_r("a", 1.0, language="python"))
    assert not f.matches(_r("b", 1.0, language="go"))
    assert not f.matches(_r("c", 1.0))  # missing key does NOT match a set filter


def test_pipeline_from_defaults_loads_bm25(monkeypatch):
    from unittest.mock import Mock

    from src.retrieval import pipeline

    components = {}
    for name in (
        "get_embedder", "BM25Index", "VectorStore", "DenseRetriever",
        "BM25Retriever", "QueryRewriter", "LLMReranker",
    ):
        components[name] = Mock()
        monkeypatch.setattr(pipeline, name, components[name])

    result = pipeline.RetrievalPipeline.from_defaults()

    components["BM25Index"].return_value.load.assert_called_once_with()
    components["DenseRetriever"].assert_called_once_with(
        components["get_embedder"].return_value, components["VectorStore"].return_value
    )
    components["BM25Retriever"].assert_called_once_with(components["BM25Index"].return_value)
    assert result.dense is components["DenseRetriever"].return_value
    assert result.bm25 is components["BM25Retriever"].return_value
    assert result.rewriter is components["QueryRewriter"].return_value
    assert result.reranker is components["LLMReranker"].return_value


def test_confidence_threshold():
    strong = [_r("a", 2.0 / 61.0 * 0.9)]
    weak = [_r("a", 0.0001)]
    assert is_confident(strong, threshold=0.3)
    assert not is_confident(weak, threshold=0.3)
    assert retrieval_confidence([]) == 0.0