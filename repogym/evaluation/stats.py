import math

Z95 = 1.959963984540054


def wilson_interval(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))


def mcnemar_exact(b: int, c: int) -> float:
    # b = tasks only agent A solved, c = tasks only agent B solved; two-sided exact binomial
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def cohens_kappa(pairs: list[tuple[str, str]]) -> float:
    # pairs of (rater1_label, rater2_label)
    n = len(pairs)
    if n == 0:
        return float("nan")
    labels = sorted({x for pair in pairs for x in pair})
    po = sum(a == b for a, b in pairs) / n
    pe = sum((sum(a == lab for a, _ in pairs) / n) * (sum(b == lab for _, b in pairs) / n)
             for lab in labels)
    return 1.0 if pe == 1.0 else (po - pe) / (1 - pe)


def paired_solve_comparison(solved_a: dict[str, bool], solved_b: dict[str, bool]) -> dict:
    tasks = sorted(set(solved_a) & set(solved_b))
    b = sum(1 for t in tasks if solved_a[t] and not solved_b[t])
    c = sum(1 for t in tasks if not solved_a[t] and solved_b[t])
    return {"n_shared": len(tasks), "only_a": b, "only_b": c, "p_mcnemar": mcnemar_exact(b, c)}
