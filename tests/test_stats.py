import math

from repogym.evaluation.stats import mcnemar_exact, paired_solve_comparison, wilson_interval


def test_wilson_basics():
    lo, hi = wilson_interval(0, 0)
    assert (lo, hi) == (0.0, 1.0)
    lo, hi = wilson_interval(32, 50)
    assert 0.5 < lo < 0.64 < hi < 0.76
    lo, hi = wilson_interval(50, 50)
    assert lo > 0.9 and hi == 1.0


def test_mcnemar_exact():
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(5, 5) == 1.0
    # 10 vs 0 discordant is significant
    assert mcnemar_exact(10, 0) < 0.01
    assert math.isclose(mcnemar_exact(1, 0), 1.0)


def test_paired_comparison():
    a = {"t1": True, "t2": True, "t3": False}
    b = {"t1": True, "t2": False, "t3": False, "t4": True}
    r = paired_solve_comparison(a, b)
    assert r["n_shared"] == 3
    assert r["only_a"] == 1 and r["only_b"] == 0
