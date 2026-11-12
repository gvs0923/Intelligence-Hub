from src.retrieval.base import RetrievalResult


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievalResult]],
    k: int = 60,
) -> list[RetrievalResult]:
    """score(doc) = Σ over lists of 1 / (k + rank_in_list).

    Ranks are 0-based here, so rank 0 (best) contributes 1/(k+1).
    The score field of each merged result is replaced with its RRF score.
    """
    scores: dict[str, float] = {}
    best: dict[str, RetrievalResult] = {}

    for results in ranked_lists:
        for rank, r in enumerate(results):
            vid = r.metadata["vector_id"]
            scores[vid] = scores.get(vid, 0.0) + 1.0 / (k + rank + 1)
            if vid not in best:
                best[vid] = r

    fused = sorted(best.values(), key=lambda r: scores[r.metadata["vector_id"]], reverse=True)
    for r in fused:
        r.score = scores[r.metadata["vector_id"]]
    return fused