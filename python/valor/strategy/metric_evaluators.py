"""Metric evaluation engine: judge individual metrics and aggregate dimensions.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

from valor.strategy.industry_clusters import DimensionSpec, MetricJudge, MetricSpec


def evaluate_metric(spec: MetricSpec, value: float, metrics: dict) -> bool:
    """Judge a single metric value against its spec.

    For dynamic_baseline: if metrics[baseline] exists and > 0, use it as threshold
    instead of spec.threshold, multiplied by spec.baseline_multiplier.

    For TREND_UP / TREND_DOWN: the data layer pre-populates metrics[field+"_prev"]
    with the prior period value.
    """
    threshold = spec.threshold
    if spec.dynamic_baseline and spec.dynamic_baseline in metrics:
        baseline = metrics.get(spec.dynamic_baseline)
        if baseline is not None and baseline > 0:
            threshold = baseline * (spec.baseline_multiplier or 1.0)

    if spec.judge == MetricJudge.THRESHOLD_GT:
        return value > (threshold or 0)
    if spec.judge == MetricJudge.THRESHOLD_LT:
        return value < (threshold or 0)
    if spec.judge == MetricJudge.RANGE:
        return (spec.threshold_low or 0) < value < (spec.threshold_high or 0)
    if spec.judge == MetricJudge.TREND_UP:
        prev = metrics.get(f"{spec.field}_prev")
        if prev is None:
            return False
        return value > prev
    if spec.judge == MetricJudge.TREND_DOWN:
        prev = metrics.get(f"{spec.field}_prev")
        if prev is None:
            return False
        return value < prev
    return False


def evaluate_dimension(dim: DimensionSpec, metrics: dict) -> tuple[str, str, list[dict]]:
    """Evaluate all metrics in a dimension, aggregate to signal via rule.

    Returns:
        (signal, details_string, per_metric_results)

    signal is one of "bullish", "bearish", "neutral".
    details_string is a human-readable summary.
    per_metric_results is a list of dicts with keys: label, value, passed,
    reference_only, and optionally skipped/missing_signal.
    """
    results: list[dict] = []
    for spec in dim.metrics:
        value = metrics.get(spec.field)
        if value is None or value == 0:
            results.append({
                "label": spec.label,
                "value": None,
                "passed": False,
                "skipped": True,
                "reference_only": spec.reference_only,
                "missing_signal": spec.missing_signal,
            })
            continue
        passed = evaluate_metric(spec, value, metrics)
        results.append({
            "label": spec.label,
            "value": value,
            "passed": passed,
            "reference_only": spec.reference_only,
        })

    voting = [r for r in results if not r.get("reference_only") and not r.get("skipped")]
    if not voting:
        return "neutral", _build_details(results), results

    passed_count = sum(1 for r in voting if r.get("passed"))
    total = len(voting)

    if dim.rule == "majority":
        if passed_count > total / 2:
            signal = "bullish"
        elif passed_count == 0:
            signal = "bearish"
        else:
            signal = "neutral"
    elif dim.rule == "all":
        signal = "bullish" if passed_count == total else "neutral"
    elif dim.rule == "any":
        signal = "bullish" if passed_count > 0 else "bearish"
    else:
        signal = "neutral"

    return signal, _build_details(results), results


def _build_details(results: list[dict]) -> str:
    parts = []
    for r in results:
        if r.get("skipped"):
            parts.append(f"{r['label']}: N/A")
        else:
            mark = "✓" if r.get("passed") else "✗"
            ref = " (参考)" if r.get("reference_only") else ""
            parts.append(f"{r['label']}: {r['value']}{ref} {mark}")
    return ", ".join(parts)