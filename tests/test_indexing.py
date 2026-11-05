from src.indexing.indexer import Indexer


class FakeEmbedder:
    @property
    def dimension(self):
        return 3

    def embed(self, texts):
        return [[float(len(t)), 1.0, 0.0] for t in texts]  # deterministic, no model


def test_index_and_query(tmp_path):
    from src.indexing.bm25 import BM25Index
    from src.indexing.vector_store import VectorStore

    indexer = Indexer(FakeEmbedder(), VectorStore(str(tmp_path / "chroma")), BM25Index(str(tmp_path / "bm25.pkl")))
    indexer.index_chunks(
        ["c1", "c2"],
        ["pod was evicted for exceeding memory limits", "dns resolution failed"],
        [{"source_path": "a.md"}, {"source_path": "b.md"}],
    )
    assert indexer.vector_store.count() == 2

    query_embedding = FakeEmbedder().embed(["pod was evicted for exceeding memory limits"])[0]
    res = indexer.vector_store.query(query_embedding, top_k=1)
    assert res["ids"][0][0] == "c1"  # longer text = higher first coordinate

    indexer.rebuild_bm25([("c1", "pod was evicted"), ("c2", "dns failed")])
    assert indexer.bm25.query("evicted", 1)[0][0] == "c1"


def test_dimension_mismatch_raises(tmp_path):
    from src.indexing.bm25 import BM25Index
    from src.indexing.vector_store import VectorStore

    store = VectorStore(str(tmp_path / "chroma"))
    indexer = Indexer(FakeEmbedder(), store, BM25Index(str(tmp_path / "bm.pkl")))
    indexer.index_chunks(["c1"], ["text"], [{}])

    class DifferentDim(FakeEmbedder):
        @property
        def dimension(self):
            return 999

    import pytest
    bad = Indexer(DifferentDim(), store, BM25Index(str(tmp_path / "bm2.pkl")))
    with pytest.raises(RuntimeError, match="dim mismatch"):
        bad.index_chunks(["c2"], ["other"], [{}])