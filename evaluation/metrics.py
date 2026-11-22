import math

Matches = list[set[int]]


def recall_at_k(matches: Matches, n_targets: int, k: int) -> float:
    found = set().union(*matches[:k])
    return len(found) / n_targets if n_targets else 0.0


def reciprocal_rank(matches: Matches) -> float:
    rank = next((rank for rank, m in enumerate(matches, 1) if m), None)
    return 1.0 / rank if rank else 0.0


def ndcg_at_k(matches: Matches, grades: list[int], k: int) -> float:
    credited: set[int] = set()
    dcg = 0.0
    for i, m in enumerate(matches[:k]):
        new = m - credited
        if new:
            dcg += (2 ** max(grades[t] for t in new) - 1) / math.log2(i + 2)
            credited |= new
    ideal = sorted(grades, reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    pos = (len(s) - 1) * p / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0