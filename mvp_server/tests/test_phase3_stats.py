from bench.phase3_common import linear_slope, percentile


def test_percentile_basic() -> None:
    values = [1.0, 2.0, 3.0, 4.0]
    assert percentile(values, 0.50) == 2.5
    assert percentile(values, 0.95) > 3.0


def test_linear_slope_non_divergent() -> None:
    samples = [(0.0, 2.0), (1.0, 2.0), (2.0, 2.0)]
    assert abs(linear_slope(samples)) < 1e-9


def test_linear_slope_positive() -> None:
    samples = [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0)]
    assert linear_slope(samples) > 0.9
