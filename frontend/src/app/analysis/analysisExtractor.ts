import { AGENT_ANALYSIS_KEYS } from "./constants";

export type Signal = "bullish" | "bearish" | "neutral";

export interface SubSignal {
  label: string;
  signal?: Signal;
  confidence?: number | string;
  details?: string;
  metrics?: Record<string, unknown>;
}

export interface MetricGroup {
  label: string;
  rows: { label: string; value: unknown }[];
}

export interface AnalysisResult {
  signal?: Signal;
  confidence?: number | string;
  reasoning?: string;
  metrics?: Record<string, unknown>;
  metricGroups?: MetricGroup[];
  riskFlags?: string[];
  subSignals?: SubSignal[];
}

const SUB_SIGNAL_LABELS: Record<string, string> = {
  // Fundamentals
  profitability_signal: "盈利能力",
  growth_signal: "成长性",
  financial_health_signal: "财务健康",
  price_ratios_signal: "估值比率",
  // Valuation
  dcf_analysis: "DCF 分析",
  owner_earnings_analysis: "所有者收益",
  // Technicals / strategy_signals
  trend_following: "趋势跟踪",
  mean_reversion: "均值回归",
  momentum: "动量",
  volatility: "波动率",
  statistical_arbitrage: "统计套利",
};

const SIGNAL_ZH: Record<Signal, string> = {
  bullish: "看涨",
  bearish: "看跌",
  neutral: "中性",
};

const METRIC_GROUP_LABELS: Record<string, string> = {
  risk_metrics: "风险指标",
  debate_analysis: "辩论分析",
  stress_test_results: "压力测试",
  strategy_signals: "策略信号",
  turnover: "成交分析",
};

const METRIC_KEY_LABELS: Record<string, string> = {
  // risk_metrics
  volatility: "年化波动率",
  value_at_risk_95: "VaR(95%)",
  max_drawdown: "最大回撤",
  market_risk_score: "市场风险评分",
  // debate_analysis
  bull_confidence: "多头置信度",
  bear_confidence: "空头置信度",
  debate_confidence: "综合置信度",
  debate_signal: "辩论信号",
  // top-level risk fields
  max_position_size: "最大仓位",
  risk_score: "风险评分",
  trading_action: "建议操作",
  // stress test
  potential_loss: "潜在损失",
  portfolio_impact: "组合影响",
  // macro
  macro_environment: "宏观环境",
  industry_outlook: "行业前景",
  policy_impact: "政策影响",
  // capital sentiment
  sentiment: "市场情绪",
  capital_flow: "资金流向",
  institutional_activity: "机构活跃度",
  turnover_analysis: "成交分析",
};

const PERCENT_KEYS = new Set([
  "volatility", "value_at_risk_95", "max_drawdown",
  "bull_confidence", "bear_confidence", "debate_confidence",
  "portfolio_impact", "confidence",
]);

const CURRENCY_KEYS = new Set([
  "potential_loss", "max_position_size",
]);

const FLAT_SIGNAL_FIELDS: Record<string, { field: string; label: string }[]> = {
  capital_sentiment: [
    { field: "sentiment", label: "市场情绪" },
    { field: "capital_flow", label: "资金流向" },
    { field: "institutional_activity", label: "机构活跃度" },
  ],
  macro_industry: [
    { field: "macro_environment", label: "宏观环境" },
    { field: "industry_outlook", label: "行业前景" },
    { field: "policy_impact", label: "政策影响" },
  ],
};

function safeStr(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  return String(v);
}

function asConf(v: unknown): number | string | undefined {
  if (typeof v === "number" || typeof v === "string") return v;
  return undefined;
}

function _prettifyKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function _labelFor(key: string): string {
  return METRIC_KEY_LABELS[key] ?? _prettifyKey(key);
}

function _normalizeSignal(v: unknown): Signal | undefined {
  if (!v) return undefined;
  const s = String(v).toLowerCase().trim();
  if (s.includes("bull") || s === "positive" || s === "favorable" || s === "buy" || s === "active") return "bullish";
  if (s.includes("bear") || s === "negative" || s === "unfavorable" || s === "sell" || s === "dormant" || s === "reduce") return "bearish";
  if (s === "neutral" || s === "normal" || s === "quiet" || s === "hold" || s === "wait") return "neutral";
  return undefined;
}

/** Format a metric value for display. Knows about percentage/currency keys. */
export function formatMetricValue(key: string, value: unknown): string {
  if (value == null) return "";
  if (typeof value === "number") {
    if (PERCENT_KEYS.has(key)) {
      return `${(value * 100).toFixed(2)}%`;
    }
    if (CURRENCY_KEYS.has(key)) {
      return `¥${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
    }
    if (Number.isInteger(value)) return String(value);
    return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  if (typeof value === "object") {
    try { return JSON.stringify(value); } catch { return String(value); }
  }
  return String(value);
}

/** Extract a sub-signal from a nested object that has signal/details/metrics fields. */
function _extractSubSignal(key: string, obj: Record<string, unknown>): SubSignal | null {
  const hasSignal = "signal" in obj || "sentiment" in obj;
  const hasDetails = typeof obj["details"] === "string";
  const hasMetrics = typeof obj["metrics"] === "object" && obj["metrics"] !== null;
  if (!hasSignal && !hasDetails && !hasMetrics) return null;

  const metrics = hasMetrics ? (obj["metrics"] as Record<string, unknown>) : undefined;
  return {
    label: SUB_SIGNAL_LABELS[key] ?? _labelFor(key),
    signal: _normalizeSignal(obj["signal"] ?? obj["sentiment"]),
    confidence: asConf(obj["confidence"]),
    details: hasDetails ? (obj["details"] as string) : undefined,
    metrics: metrics && Object.keys(metrics).length ? metrics : undefined,
  };
}

/** If a nested object is itself a container of sub-signals (e.g. strategy_signals), extract them. */
function _extractSubSignalsFromContainer(container: Record<string, unknown>): SubSignal[] {
  const result: SubSignal[] = [];
  for (const [k, v] of Object.entries(container)) {
    if (v && typeof v === "object" && !Array.isArray(v)) {
      const sub = _extractSubSignal(k, v as Record<string, unknown>);
      if (sub) result.push(sub);
    }
  }
  return result;
}

/** Build a metric group from a flat object of primitives. */
function _buildMetricGroup(groupKey: string, obj: Record<string, unknown>): MetricGroup | null {
  const rows: { label: string; value: unknown }[] = [];
  for (const [k, v] of Object.entries(obj)) {
    if (v == null) continue;
    if (typeof v === "object") continue; // skip nested objects; they get their own group
    rows.push({ label: _labelFor(k), value: formatMetricValue(k, v) });
  }
  if (rows.length === 0) return null;
  return { label: METRIC_GROUP_LABELS[groupKey] ?? _prettifyKey(groupKey), rows };
}

function _generateSummary(
  signal: Signal | undefined,
  confidence: number | string | undefined,
  subSignals: SubSignal[] | undefined,
): string | undefined {
  if (!signal) return undefined;
  const confidenceStr =
    typeof confidence === "number"
      ? confidence <= 1
        ? `${Math.round(confidence * 100)}%`
        : `${confidence}%`
      : confidence ?? "";

  if (!subSignals || subSignals.length === 0) {
    return `综合信号: ${SIGNAL_ZH[signal]}${confidenceStr ? ` (${confidenceStr})` : ""}`;
  }

  const bull = subSignals.filter((s) => s.signal === "bullish").length;
  const bear = subSignals.filter((s) => s.signal === "bearish").length;
  const neutral = subSignals.length - bull - bear;
  return `综合信号: ${SIGNAL_ZH[signal]}${confidenceStr ? ` (${confidenceStr})` : ""}。${subSignals.length} 项子信号中 ${bull} 项偏多、${bear} 项偏空、${neutral} 项中性。`;
}

/** Detect if a state dict already looks like an analysis payload (for bull_bear_debate sub-events). */
function _looksLikeAnalysis(state: Record<string, unknown>): boolean {
  return "signal" in state || "sentiment" in state || "reasoning" in state || "key_points" in state;
}

/** Extract normalized analysis result from an agent's state_delta. */
export function extractAnalysisResult(
  agentName: string,
  state: Record<string, unknown> | undefined | null,
): AnalysisResult | null {
  if (!state) return null;

  const stateData = (state["data"] as Record<string, unknown>) ?? {};

  // 1) For agents that store analysis under a named key in data
  const analysisKey = AGENT_ANALYSIS_KEYS[agentName];
  if (analysisKey) {
    const analysis = stateData[analysisKey] as Record<string, unknown> | undefined;
    if (analysis) {
      return _parseAnalysisDict(analysis, agentName);
    }
  }

  // 2) For market_data: no signal/confidence, derive from data
  if (agentName === "market_data") {
    return _extractMarketData(stateData);
  }

  // 3) For portfolio_manager: decision stored in metadata
  if (agentName === "portfolio_manager") {
    return _extractPortfolioDecision(state);
  }

  // 4) For bull_bear_debate sub-events: state itself is the analysis dict
  //    (signal/confidence/reasoning/key_points at top level, not wrapped in {data: {...}})
  if (_looksLikeAnalysis(state)) {
    return _parseAnalysisDict(state, agentName);
  }

  // 5) Fallback: try to find analysis from messages
  return _extractFromMessages(state, agentName);
}

function _parseAnalysisDict(
  analysis: Record<string, unknown>,
  agentName: string = "",
): AnalysisResult | null {
  const signal = _normalizeSignal(analysis["signal"] ?? analysis["sentiment"]);
  const confidence = analysis["confidence"] ?? undefined;
  const riskFlags = _extractRiskFlags(analysis);

  const skipKeys = new Set([
    "signal", "sentiment", "confidence", "reasoning", "risk_flags", "riskFlags",
    "key_points", "key_factors",
  ]);
  const metrics: Record<string, unknown> = {};
  const metricGroups: MetricGroup[] = [];
  const subSignals: SubSignal[] = [];
  let reasoningText: string | undefined;

  // reasoning can be a string (use as-is) or a dict of sub-signals (extract each)
  const rawReasoning = analysis["reasoning"];
  if (typeof rawReasoning === "string") {
    reasoningText = rawReasoning.trim() || undefined;
  } else if (rawReasoning && typeof rawReasoning === "object" && !Array.isArray(rawReasoning)) {
    for (const [k, v] of Object.entries(rawReasoning as Record<string, unknown>)) {
      if (v && typeof v === "object" && !Array.isArray(v)) {
        const sub = _extractSubSignal(k, v as Record<string, unknown>);
        if (sub) subSignals.push(sub);
      }
    }
  }

  // Agent-specific flat signal fields (capital_sentiment, macro_industry)
  // These are primitive strings like "neutral", not nested objects. Promote to sub-signals.
  const flatFields = FLAT_SIGNAL_FIELDS[agentName];
  if (flatFields) {
    for (const { field, label } of flatFields) {
      const v = analysis[field];
      if (v == null || v === "") continue;
      const sig = _normalizeSignal(v);
      subSignals.push({
        label,
        signal: sig,
        details: safeStr(v),
      });
      skipKeys.add(field);
    }
  }

  // Collect other fields: nested objects become sub-signals or metric groups,
  // primitives become metrics.
  for (const [k, v] of Object.entries(analysis)) {
    if (skipKeys.has(k)) continue;
    if (v == null) continue;

    if (Array.isArray(v)) {
      // key_points / key_factors / risk_flags-style arrays: render as metrics (joined string)
      if (v.length > 0) {
        metrics[_labelFor(k)] = v.map(safeStr).join("、");
      }
      continue;
    }

    if (typeof v === "object") {
      const container = v as Record<string, unknown>;
      // First check if it's a container of sub-signals (e.g. strategy_signals)
      const subs = _extractSubSignalsFromContainer(container);
      if (subs.length > 0) {
        subSignals.push(...subs);
        continue;
      }
      // Then check if it's a single sub-signal
      const sub = _extractSubSignal(k, container);
      if (sub) {
        subSignals.push(sub);
        continue;
      }
      // Otherwise, treat as a metric group (e.g. risk_metrics, debate_analysis, stress_test_results)
      // Recursively: each nested object scenario becomes its own sub-group
      const nestedGroups = _extractNestedMetricGroups(k, container);
      if (nestedGroups.length > 0) {
        metricGroups.push(...nestedGroups);
        continue;
      }
      const group = _buildMetricGroup(k, container);
      if (group) metricGroups.push(group);
    } else {
      metrics[_labelFor(k)] = formatMetricValue(k, v);
    }
  }

  // If no explicit reasoning text, synthesize a summary from signal + sub-signals
  if (!reasoningText) {
    reasoningText = _generateSummary(signal, asConf(confidence), subSignals);
  }

  return {
    signal,
    confidence: asConf(confidence),
    reasoning: reasoningText,
    metrics: Object.keys(metrics).length ? metrics : undefined,
    metricGroups: metricGroups.length ? metricGroups : undefined,
    riskFlags,
    subSignals: subSignals.length ? subSignals : undefined,
  };
}

/** For objects like stress_test_results: {market_crash: {...}, moderate_decline: {...}} - each scenario becomes a group. */
function _extractNestedMetricGroups(parentKey: string, container: Record<string, unknown>): MetricGroup[] {
  const groups: MetricGroup[] = [];
  let hasNested = false;
  for (const [k, v] of Object.entries(container)) {
    if (v && typeof v === "object" && !Array.isArray(v)) {
      hasNested = true;
      const sub = v as Record<string, unknown>;
      const group = _buildMetricGroup(k, sub);
      if (group) {
        const parentLabel = METRIC_GROUP_LABELS[parentKey] ?? _prettifyKey(parentKey);
        group.label = `${parentLabel}: ${group.label}`;
        groups.push(group);
      }
    }
  }
  return hasNested ? groups : [];
}

function _extractRiskFlags(analysis: Record<string, unknown>): string[] {
  const raw = analysis["risk_flags"] ?? analysis["riskFlags"] ?? [];
  if (Array.isArray(raw)) return raw.map(safeStr).filter(Boolean);
  return [];
}

function _extractMarketData(data: Record<string, unknown>): AnalysisResult | null {
  const metrics: Record<string, unknown> = {};
  const marketCap = data["market_cap"];
  if (marketCap != null && Number(marketCap) > 0) {
    metrics["市值"] = _fmtCurrency(Number(marketCap));
  }

  const prices = data["prices"] as Array<Record<string, unknown>> | undefined;
  if (prices && prices.length > 0) {
    const closes = prices.map((p) => Number(p["close"])).filter(Number.isFinite);
    const volumes = prices.map((p) => Number(p["volume"])).filter(Number.isFinite);
    if (closes.length > 0) {
      const maxClose = Math.max(...closes);
      const minClose = Math.min(...closes);
      const avgClose = closes.reduce((a, b) => a + b, 0) / closes.length;
      metrics["最高价"] = maxClose.toFixed(2);
      metrics["最低价"] = minClose.toFixed(2);
      metrics["均价"] = avgClose.toFixed(2);
      metrics["数据天数"] = closes.length;
    }
    if (volumes.length > 0) {
      metrics["日均成交量"] = Math.round(volumes.reduce((a, b) => a + b, 0) / volumes.length).toLocaleString();
    }
  }

  const startDate = data["start_date"];
  const endDate = data["end_date"];
  let reasoning = "";
  if (startDate && endDate) {
    reasoning = `分析区间: ${startDate} 至 ${endDate}`;
  }

  return {
    reasoning: reasoning || undefined,
    metrics: Object.keys(metrics).length ? metrics : undefined,
  };
}

function _extractPortfolioDecision(state: Record<string, unknown>): AnalysisResult | null {
  const meta = state["metadata"] as Record<string, unknown> | undefined;
  const decision = meta?.["portfolio_management_agent_decision_details"] as Record<string, unknown> | undefined;
  if (!decision) return null;

  return {
    signal: _normalizeSignal(decision["action"]),
    confidence: asConf(decision["confidence"]),
    reasoning: (decision["reasoning_snippet"] as string) ?? undefined,
    metrics: {
      "操作": decision["action"] ?? "N/A",
      "数量": decision["quantity"] ?? "N/A",
    },
  };
}

function _extractFromMessages(
  state: Record<string, unknown>,
  agentName: string,
): AnalysisResult | null {
  const messages = state["messages"];
  if (!Array.isArray(messages) || messages.length === 0) return null;

  // Try to find the last message with a parseable JSON content
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    const content = _getMessageContent(msg);
    if (!content) continue;

    // Try to parse as JSON
    try {
      const parsed = typeof content === "string" ? JSON.parse(content) : content;
      if (parsed && typeof parsed === "object") {
        return _parseAnalysisDict(parsed as Record<string, unknown>, agentName);
      }
    } catch {
      // Not JSON, try to extract structured info from the string
      const text = String(content);
      if (text.length > 20 && text.length < 5000) {
        return { reasoning: text };
      }
    }
  }

  return null;
}

function _getMessageContent(msg: unknown): string | undefined {
  if (msg == null) return undefined;
  if (typeof msg === "string") return msg;
  if (typeof msg === "object") {
    const m = msg as Record<string, unknown>;
    // LangChain serialized message
    if (typeof m["content"] === "string") return m["content"];
    // Python str() representation: content='...' name='...'
    const str = String(m);
    const match = str.match(/content='((?:[^'\\]|\\.)*)'/);
    if (match) return match[1];
    return str;
  }
  return String(msg);
}

function _fmtCurrency(v: number): string {
  if (v >= 1e12) return `${(v / 1e12).toFixed(2)}万亿`;
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)}亿`;
  if (v >= 1e4) return `${(v / 1e4).toFixed(2)}万`;
  return v.toFixed(2);
}
