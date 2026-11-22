from evaluation.evaluator import Target, load_golden
from evaluation.metrics import ndcg_at_k, percentile, recall_at_k, reciprocal_rank
from src.retrieval.base import RetrievalResult


def test_rank_metrics():
    matches = [set(), {0}, set(), {1}]  # target 0 at rank 2, target 1 at rank 4
    assert reciprocal_rank(matches) == 0.5
    assert recall_at_k(matches, 2, 2) == 0.5
    assert recall_at_k(matches, 2, 10) == 1.0
    assert reciprocal_rank([set(), set()]) == 0.0


def test_ndcg_perfect_and_duplicate_chunks():
    assert ndcg_at_k([{0}, {1}], [3, 3], 10) == 1.0
    assert ndcg_at_k([{0}, {0}], [3], 10) == 1.0  # 2nd chunk of same file earns nothing extra
    assert ndcg_at_k([set(), {0}], [3], 10) < 1.0


def test_percentile_interpolates():
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([], 95) == 0.0


def test_target_matches_path_and_text():
    r = RetrievalResult(
        content="public static ApiClient fromCluster()", score=1.0,
        metadata={"source_path": "/app/corpus/java/util/Config.java"},
    )
    assert Target(path="util/Config.java", contains="fromcluster").matches(r)
    assert not Target(path="util/KubeConfig.java").matches(r)


def test_golden_set_is_valid_and_large_enough():
    assert len(load_golden()) >= 50