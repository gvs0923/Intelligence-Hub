from src.retrieval.base import RetrievalResult


def retrieval_confidence(results: list[RetrievalResult]) -> float:
    """Top RRF score normalized to a rough 0-1 confidence.

    RRF max per list is 1/(k+1); a doc ranked #1 in both lists scores ~2/61 ≈ 0.033.
    We normalize by the theoretical max for 2 lists (k=60): 2/(61).
    """
    if not results:
        return 0.0
    theoretical_max = 2.0 / 61.0  # rank 0 in both lists, k=60
    return min(results[0].score / theoretical_max, 1.0)


def is_confident(results: list[RetrievalResult], threshold: float) -> bool:
    return retrieval_confidence(results) >= threshold