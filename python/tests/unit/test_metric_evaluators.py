"""Unit tests for metric_evaluators.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from valor.strategy.industry_clusters import (
    DimensionSpec,
    MetricJudge,
    MetricSpec,
)
from valor.strategy.metric_evaluators import evaluate_dimension, evaluate_metric


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gt_spec(field="x", threshold=0.5):
    return MetricSpec(field=field, label=field, judge=MetricJudge.THRESHOLD_GT,
                      threshold=threshold)


def _lt_spec(field="x", threshold=0.5):
    return MetricSpec(field=field, label=field, judge=MetricJudge.THRESHOLD_LT,
                      threshold=threshold)


# ---------------------------------------------------------------------------
# evaluate_metric - THRESHOLD_GT
# ---------------------------------------------------------------------------


def test_threshold_gt_passes_when_above():
    assert evaluate_metric(_gt_spec(threshold=0.5), 0.6, {}) is True


def test_threshold_gt_fails_when_below():
    assert evaluate_metric(_gt_spec(threshold=0.5), 0.4, {}) is False


def test_threshold_gt_edge_at_threshold():
    """Equal to threshold is NOT greater, so should fail."""
    assert evaluate_metric(_gt_spec(threshold=0.5), 0.5, {}) is False


# ---------------------------------------------------------------------------
# evaluate_metric - THRESHOLD_LT
# ---------------------------------------------------------------------------


def test_threshold_lt_passes_when_below():
    assert evaluate_metric(_lt_spec(threshold=0.5), 0.4, {}) is True


def test_threshold_lt_fails_when_above():
    assert evaluate_metric(_lt_spec(threshold=0.5), 0.6, {}) is False


def test_threshold_lt_edge_at_threshold():
    """Equal to threshold is NOT less, so should fail."""
    assert evaluate_metric(_lt_spec(threshold=0.5), 0.5, {}) is False


# ---------------------------------------------------------------------------
# evaluate_metric - RANGE
# ---------------------------------------------------------------------------


def test_range_passes_within_bounds():
    spec = MetricSpec(field="x", label="x", judge=MetricJudge.RANGE,
                      threshold_low=0.1, threshold_high=0.9)
    assert evaluate_metric(spec, 0.5, {}) is True
    assert evaluate_metric(spec, 0.05, {}) is False
    assert evaluate_metric(spec, 0.95, {}) is False


def test_range_edge_at_boundaries():
    """Equal to boundary is NOT within range (strict inequality)."""
    spec = MetricSpec(field="x", label="x", judge=MetricJudge.RANGE,
                      threshold_low=0.1, threshold_high=0.9)
    assert evaluate_metric(spec, 0.1, {}) is False
    assert evaluate_metric(spec, 0.9, {}) is False


# ---------------------------------------------------------------------------
# evaluate_metric - dynamic_baseline
# ---------------------------------------------------------------------------


def test_dynamic_baseline_overrides_threshold():
    spec = MetricSpec(field="nim", label="NIM", judge=MetricJudge.THRESHOLD_GT,
                      threshold=0.014, dynamic_baseline="industry_avg_nim")
    # 动态基准 0.016 存在, value 0.015 > 0.016? 否 -> False
    assert evaluate_metric(spec, 0.015, {"industry_avg_nim": 0.016}) is False
    # value 0.017 > 0.016 -> True
    assert evaluate_metric(spec, 0.017, {"industry_avg_nim": 0.016}) is True


def test_dynamic_baseline_falls_back_to_threshold_when_missing():
    spec = MetricSpec(field="nim", label="NIM", judge=MetricJudge.THRESHOLD_GT,
                      threshold=0.014, dynamic_baseline="industry_avg_nim")
    # 基准缺失, 回退到 threshold=0.014
    assert evaluate_metric(spec, 0.015, {}) is True


def test_dynamic_baseline_falls_back_when_baseline_zero():
    spec = MetricSpec(field="nim", label="NIM", judge=MetricJudge.THRESHOLD_GT,
                      threshold=0.014, dynamic_baseline="industry_avg_nim")
    assert evaluate_metric(spec, 0.015, {"industry_avg_nim": 0}) is True


def test_dynamic_baseline_falls_back_when_baseline_none():
    spec = MetricSpec(field="nim", label="NIM", judge=MetricJudge.THRESHOLD_GT,
                      threshold=0.014, dynamic_baseline="industry_avg_nim")
    assert evaluate_metric(spec, 0.015, {"industry_avg_nim": None}) is True


def test_baseline_multiplier():
    """dynamic_baseline with multiplier: value > baseline * multiplier."""
    spec = MetricSpec(field="fcf_ps", label="FCF/EPS",
                      judge=MetricJudge.THRESHOLD_GT, threshold=0.0,
                      dynamic_baseline="eps", baseline_multiplier=0.8)
    # fcf_ps=1.0, eps=2.0 -> threshold=2.0*0.8=1.6, 1.0 > 1.6? False
    assert evaluate_metric(spec, 1.0, {"eps": 2.0}) is False
    # fcf_ps=2.0, eps=2.0 -> threshold=1.6, 2.0 > 1.6? True
    assert evaluate_metric(spec, 2.0, {"eps": 2.0}) is True


def test_baseline_multiplier_with_lt_judge():
    """Multiplier applies to LT judge as well."""
    spec = MetricSpec(field="debt", label="Debt",
                      judge=MetricJudge.THRESHOLD_LT, threshold=1.0,
                      dynamic_baseline="industry_avg", baseline_multiplier=1.5)
    # debt=1.0, industry_avg=0.5 -> threshold=0.5*1.5=0.75, 1.0 < 0.75? False
    assert evaluate_metric(spec, 1.0, {"industry_avg": 0.5}) is False
    # debt=0.5, threshold=0.75, 0.5 < 0.75? True
    assert evaluate_metric(spec, 0.5, {"industry_avg": 0.5}) is True


# ---------------------------------------------------------------------------
# evaluate_metric - TREND_UP / TREND_DOWN
# ---------------------------------------------------------------------------


def test_trend_up_passes_when_rising():
    spec = MetricSpec(field="revenue", label="Revenue",
                      judge=MetricJudge.TREND_UP)
    assert evaluate_metric(spec, 120, {"revenue_prev": 100}) is True


def test_trend_up_fails_when_falling():
    spec = MetricSpec(field="revenue", label="Revenue",
                      judge=MetricJudge.TREND_UP)
    assert evaluate_metric(spec, 90, {"revenue_prev": 100}) is False


def test_trend_up_fails_when_prev_missing():
    spec = MetricSpec(field="revenue", label="Revenue",
                      judge=MetricJudge.TREND_UP)
    assert evaluate_metric(spec, 120, {}) is False


def test_trend_down_passes_when_falling():
    spec = MetricSpec(field="cost", label="Cost",
                      judge=MetricJudge.TREND_DOWN)
    assert evaluate_metric(spec, 80, {"cost_prev": 100}) is True


def test_trend_down_fails_when_rising():
    spec = MetricSpec(field="cost", label="Cost",
                      judge=MetricJudge.TREND_DOWN)
    assert evaluate_metric(spec, 120, {"cost_prev": 100}) is False


def test_trend_down_fails_when_prev_missing():
    spec = MetricSpec(field="cost", label="Cost",
                      judge=MetricJudge.TREND_DOWN)
    assert evaluate_metric(spec, 80, {}) is False


# ---------------------------------------------------------------------------
# evaluate_metric - NaN
# ---------------------------------------------------------------------------


def test_nan_value_returns_false():
    """NaN comparisons always return False in Python."""
    spec = _gt_spec(threshold=0.5)
    assert evaluate_metric(spec, float("nan"), {}) is False


def test_nan_value_with_range():
    spec = MetricSpec(field="x", label="x", judge=MetricJudge.RANGE,
                      threshold_low=0.1, threshold_high=0.9)
    assert evaluate_metric(spec, float("nan"), {}) is False


# ---------------------------------------------------------------------------
# evaluate_dimension - majority rule
# ---------------------------------------------------------------------------


def test_evaluate_dimension_majority_bullish():
    dim = DimensionSpec(name="d", label="d", weight=0.5, rule="majority", metrics=[
        _gt_spec(field="a", threshold=0.5),
        _gt_spec(field="b", threshold=0.5),
        _gt_spec(field="c", threshold=0.5),
    ])
    # 2/3 passed -> bullish
    signal, details, results = evaluate_dimension(dim, {"a": 0.6, "b": 0.6, "c": 0.4})
    assert signal == "bullish"
    assert len(results) == 3


def test_evaluate_dimension_majority_bearish_all_fail():
    dim = DimensionSpec(name="d", label="d", weight=0.5, rule="majority", metrics=[
        _gt_spec(field="a", threshold=0.5),
        _gt_spec(field="b", threshold=0.5),
    ])
    signal, _, _ = evaluate_dimension(dim, {"a": 0.1, "b": 0.1})
    assert signal == "bearish"


def test_evaluate_dimension_majority_neutral():
    dim = DimensionSpec(name="d", label="d", weight=0.5, rule="majority", metrics=[
        _gt_spec(field="a", threshold=0.5),
        _gt_spec(field="b", threshold=0.5),
    ])
    # 1/2 passed -> neutral (not >= half of 2 which is 1, but not 0)
    signal, _, _ = evaluate_dimension(dim, {"a": 0.6, "b": 0.1})
    assert signal == "neutral"


def test_evaluate_dimension_majority_exact_tie():
    """2/4 passed (exactly half) -> neutral (strict majority requires > half)."""
    dim = DimensionSpec(name="d", label="d", weight=0.5, rule="majority", metrics=[
        _gt_spec(field="a", threshold=0.5),
        _gt_spec(field="b", threshold=0.5),
        _gt_spec(field="c", threshold=0.5),
        _gt_spec(field="d_m", threshold=0.5),
    ])
    signal, _, _ = evaluate_dimension(
        dim, {"a": 0.6, "b": 0.6, "c": 0.1, "d_m": 0.1})
    assert signal == "neutral"


# ---------------------------------------------------------------------------
# evaluate_dimension - all rule
# ---------------------------------------------------------------------------


def test_evaluate_dimension_all_rule_bullish():
    dim = DimensionSpec(name="d", label="d", weight=0.5, rule="all", metrics=[
        _gt_spec(field="a", threshold=0.5),
        _gt_spec(field="b", threshold=0.5),
    ])
    signal, _, _ = evaluate_dimension(dim, {"a": 0.6, "b": 0.6})
    assert signal == "bullish"


def test_evaluate_dimension_all_rule_neutral():
    dim = DimensionSpec(name="d", label="d", weight=0.5, rule="all", metrics=[
        _gt_spec(field="a", threshold=0.5),
        _gt_spec(field="b", threshold=0.5),
    ])
    signal, _, _ = evaluate_dimension(dim, {"a": 0.6, "b": 0.1})
    assert signal == "neutral"


# ---------------------------------------------------------------------------
# evaluate_dimension - any rule
# ---------------------------------------------------------------------------


def test_evaluate_dimension_any_rule_bullish():
    dim = DimensionSpec(name="d", label="d", weight=0.5, rule="any", metrics=[
        _gt_spec(field="a", threshold=0.5),
        _gt_spec(field="b", threshold=0.5),
    ])
    signal, _, _ = evaluate_dimension(dim, {"a": 0.6, "b": 0.1})
    assert signal == "bullish"


def test_evaluate_dimension_any_rule_bearish():
    dim = DimensionSpec(name="d", label="d", weight=0.5, rule="any", metrics=[
        _gt_spec(field="a", threshold=0.5),
        _gt_spec(field="b", threshold=0.5),
    ])
    signal, _, _ = evaluate_dimension(dim, {"a": 0.1, "b": 0.1})
    assert signal == "bearish"


# ---------------------------------------------------------------------------
# evaluate_dimension - reference_only
# ---------------------------------------------------------------------------


def test_reference_only_excluded_from_voting():
    dim = DimensionSpec(name="d", label="d", weight=0.5, metrics=[
        MetricSpec(field="a", label="a", judge=MetricJudge.THRESHOLD_GT, threshold=0.5),
        MetricSpec(field="b", label="b", judge=MetricJudge.THRESHOLD_GT, threshold=0.5,
                   reference_only=True),
    ])
    # a=0.6 passed (voting), b=0.1 failed (reference_only, not voting)
    # voting: 1/1 passed -> bullish
    signal, _, results = evaluate_dimension(dim, {"a": 0.6, "b": 0.1})
    assert signal == "bullish"
    assert len(results) == 2  # 参考项仍出现在结果中


def test_all_reference_only_returns_neutral():
    dim = DimensionSpec(name="d", label="d", weight=0.5, metrics=[
        MetricSpec(field="a", label="a", judge=MetricJudge.THRESHOLD_GT, threshold=0.5,
                   reference_only=True),
    ])
    signal, _, _ = evaluate_dimension(dim, {"a": 0.6})
    assert signal == "neutral"


# ---------------------------------------------------------------------------
# evaluate_dimension - missing values
# ---------------------------------------------------------------------------


def test_missing_value_skipped():
    dim = DimensionSpec(name="d", label="d", weight=0.5, metrics=[
        _gt_spec(field="a", threshold=0.5),
        _gt_spec(field="b", threshold=0.5),
    ])
    # a 缺失跳过, b passed -> voting 1/1 -> bullish
    signal, _, results = evaluate_dimension(dim, {"b": 0.6})
    assert signal == "bullish"
    skipped = [r for r in results if r.get("skipped")]
    assert len(skipped) == 1


def test_missing_value_returns_missing_signal():
    """Missing values record spec.missing_signal in result."""
    dim = DimensionSpec(name="d", label="d", weight=0.5, metrics=[
        MetricSpec(field="a", label="a", judge=MetricJudge.THRESHOLD_GT,
                   threshold=0.5, missing_signal="bearish"),
        _gt_spec(field="b", threshold=0.5),
    ])
    signal, _, results = evaluate_dimension(dim, {"b": 0.6})
    # a missing, b passed -> voting 1/1 -> bullish
    assert signal == "bullish"
    skipped = [r for r in results if r.get("skipped")]
    assert len(skipped) == 1
    assert skipped[0]["missing_signal"] == "bearish"


def test_all_metrics_missing_returns_neutral():
    dim = DimensionSpec(name="d", label="d", weight=0.5, metrics=[
        _gt_spec(field="a", threshold=0.5),
        _gt_spec(field="b", threshold=0.5),
    ])
    signal, _, results = evaluate_dimension(dim, {})
    assert signal == "neutral"
    assert all(r.get("skipped") for r in results)


def test_zero_value_treated_as_missing():
    """value=0 is treated as missing (data not available) and skipped."""
    dim = DimensionSpec(name="d", label="d", weight=0.5, metrics=[
        _gt_spec(field="a", threshold=0.5),
        _gt_spec(field="b", threshold=0.5),
    ])
    signal, _, results = evaluate_dimension(dim, {"a": 0, "b": 0.6})
    # a=0 skipped (treated as missing), b=0.6 passed -> voting 1/1 -> bullish
    assert signal == "bullish"
    skipped = [r for r in results if r.get("skipped")]
    assert len(skipped) == 1
    assert skipped[0]["label"] == "a"


# ---------------------------------------------------------------------------
# evaluate_dimension - details string
# ---------------------------------------------------------------------------


def test_details_string_format():
    dim = DimensionSpec(name="d", label="d", weight=0.5, metrics=[
        _gt_spec(field="a", threshold=0.5),
        _gt_spec(field="b", threshold=0.5),
    ])
    _, details, _ = evaluate_dimension(dim, {"a": 0.6, "b": 0.1})
    assert "a: 0.6" in details
    assert "b: 0.1" in details


def test_details_string_includes_skipped():
    dim = DimensionSpec(name="d", label="d", weight=0.5, metrics=[
        _gt_spec(field="a", threshold=0.5),
        _gt_spec(field="b", threshold=0.5),
    ])
    _, details, _ = evaluate_dimension(dim, {"b": 0.6})
    assert "a: N/A" in details


def test_details_string_includes_reference_only():
    dim = DimensionSpec(name="d", label="d", weight=0.5, metrics=[
        _gt_spec(field="a", threshold=0.5),
        MetricSpec(field="b", label="b", judge=MetricJudge.THRESHOLD_GT, threshold=0.5,
                   reference_only=True),
    ])
    _, details, _ = evaluate_dimension(dim, {"a": 0.6, "b": 0.6})
    assert "(参考)" in details


# ---------------------------------------------------------------------------
# evaluate_dimension - result dict structure
# ---------------------------------------------------------------------------


def test_result_dict_has_expected_keys():
    dim = DimensionSpec(name="d", label="d", weight=0.5, metrics=[
        _gt_spec(field="a", threshold=0.5),
    ])
    _, _, results = evaluate_dimension(dim, {"a": 0.6})
    r = results[0]
    assert r["label"] == "a"
    assert r["value"] == 0.6
    assert r["passed"] is True
    assert r["reference_only"] is False
    assert "skipped" not in r


# ---------------------------------------------------------------------------
# Conglomerate regression anchor
# ---------------------------------------------------------------------------


def test_conglomerate_fcf_compound_comparison():
    """Regression: fcf_per_share > eps * 0.8 matches legacy fundamentals.py:97-98."""
    from valor.strategy.industry_clusters import INDUSTRY_CLUSTERS

    cluster = INDUSTRY_CLUSTERS["conglomerate"]
    dims = {d.name: d for d in cluster.dimensions}
    fcf_spec = next(
        m for m in dims["financial_health"].metrics
        if m.field == "free_cash_flow_per_share"
    )
    assert fcf_spec.dynamic_baseline == "earnings_per_share"
    assert fcf_spec.baseline_multiplier == 0.8

    # case 1: fcf=1.0, eps=2.0 -> threshold=2.0*0.8=1.6, 1.0 > 1.6? False
    assert evaluate_metric(fcf_spec, 1.0, {"earnings_per_share": 2.0}) is False
    # case 2: fcf=2.0, eps=2.0 -> threshold=1.6, 2.0 > 1.6? True
    assert evaluate_metric(fcf_spec, 2.0, {"earnings_per_share": 2.0}) is True
    # case 3: fcf=1.0, eps missing -> fallback to threshold=0.0, 1.0 > 0.0? True
    assert evaluate_metric(fcf_spec, 1.0, {}) is True


def test_conglomerate_financial_health_dimension_evaluation():
    """Full financial_health dimension evaluation matching legacy behavior."""
    from valor.strategy.industry_clusters import INDUSTRY_CLUSTERS

    cluster = INDUSTRY_CLUSTERS["conglomerate"]
    dim = next(d for d in cluster.dimensions if d.name == "financial_health")

    # All 3 metrics pass: current_ratio=2.0>1.5, debt=0.3<0.5, fcf=2.0>eps*0.8=1.6
    metrics = {
        "current_ratio": 2.0,
        "debt_to_equity": 0.3,
        "free_cash_flow_per_share": 2.0,
        "earnings_per_share": 2.0,
    }
    signal, _, _ = evaluate_dimension(dim, metrics)
    assert signal == "bullish"  # 3/3 -> bullish

    # All 3 fail: current_ratio=1.0<1.5, debt=0.6>0.5, fcf=0.5<eps*0.8=1.6
    metrics2 = {
        "current_ratio": 1.0,
        "debt_to_equity": 0.6,
        "free_cash_flow_per_share": 0.5,
        "earnings_per_share": 2.0,
    }
    signal2, _, _ = evaluate_dimension(dim, metrics2)
    assert signal2 == "bearish"  # 0/3 -> bearish

    # 1/3 passes: neutral (health_score=1 in legacy)
    metrics3 = {
        "current_ratio": 1.0,
        "debt_to_equity": 0.3,
        "free_cash_flow_per_share": 0.5,
        "earnings_per_share": 2.0,
    }
    signal3, _, _ = evaluate_dimension(dim, metrics3)
    assert signal3 == "neutral"  # 1/3 -> neutral