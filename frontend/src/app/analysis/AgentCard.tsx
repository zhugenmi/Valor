import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  Loader2,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import AgentResultDisplay from "./AgentResultDisplay";
import { extractAnalysisResult } from "./analysisExtractor";
import {
  AGENT_LABEL_ZH,
  type AgentState,
  SUB_AGENT_KEYS,
  SUB_AGENT_LABEL_ZH,
} from "./constants";

interface AgentCardProps {
  name: string;
  state: AgentState | undefined;
  isActive?: boolean;
}

const CURRENT_STEP_LABELS: Record<string, string> = {
  market_data: "正在获取市场数据...",
  technicals: "正在分析技术指标...",
  fundamentals: "正在分析基本面...",
  valuation: "正在估值分析...",
  capital_sentiment: "正在分析资金情绪...",
  macro_industry: "正在分析宏观环境...",
  bull_bear_debate: "正在进行多空辩论...",
  risk_manager: "正在评估风险...",
  portfolio_manager: "正在生成综合决策...",
};

function StatusIcon({ status }: { status: AgentState["status"] | undefined }) {
  if (!status || status === "pending") {
    return <Circle className="size-4 text-muted-foreground" />;
  }
  if (status === "running") {
    return <Loader2 className="size-4 animate-spin text-blue-500" />;
  }
  if (status === "completed") {
    return <CheckCircle2 className="size-4 text-green-500" />;
  }
  return <XCircle className="size-4 text-red-500" />;
}

function SubStateRow({ subKey, data }: { subKey: string; data: unknown }) {
  const fullKey = `bull_bear_debate.${subKey}`;
  const label = SUB_AGENT_LABEL_ZH[fullKey] ?? subKey;
  const result = extractAnalysisResult(
    "bull_bear_debate",
    data as Record<string, unknown>,
  );
  const [subExpanded, setSubExpanded] = useState(false);
  const [subShowRaw, setSubShowRaw] = useState(false);

  return (
    <div className="mt-1 ml-4 border-muted border-l-2 pl-2">
      <button
        type="button"
        onClick={() => setSubExpanded(!subExpanded)}
        className="flex w-full items-center gap-1 text-left text-sm"
      >
        <CheckCircle2 className="size-3 shrink-0 text-green-500" />
        <span className="font-medium">{label}</span>
        {result?.signal && (
          <span
            className={`ml-1 text-xs ${
              result.signal === "bullish"
                ? "text-red-500"
                : result.signal === "bearish"
                  ? "text-green-500"
                  : "text-muted-foreground"
            }`}
          >
            [
            {result.signal === "bullish"
              ? "看涨"
              : result.signal === "bearish"
                ? "看跌"
                : "中性"}
            ]
          </span>
        )}
      </button>
      {subExpanded && (
        <div className="mt-1 max-h-[40vh] overflow-y-auto">
          {result ? (
            <AgentResultDisplay
              result={result}
              agentName={subKey}
              showRaw={subShowRaw}
              onToggleRaw={() => setSubShowRaw(!subShowRaw)}
              rawData={data}
            />
          ) : (
            <pre className="overflow-x-auto whitespace-pre-wrap rounded bg-muted p-2 text-xs">
              {typeof data === "string" ? data : JSON.stringify(data, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

export default function AgentCard({ name, state, isActive }: AgentCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const label = AGENT_LABEL_ZH[name] ?? name;
  const status = state?.status ?? "pending";
  const subKeys = SUB_AGENT_KEYS[name];
  const hasSubStates =
    subKeys && state?.subStates && Object.keys(state.subStates).length > 0;

  const analysisResult =
    state?.output != null && !hasSubStates
      ? extractAnalysisResult(name, state.output as Record<string, unknown>)
      : null;

  return (
    <div
      className={`rounded-lg border bg-card p-3 transition-all duration-300 ${
        isActive
          ? "border-blue-400 shadow-blue-200/50 shadow-md ring-1 ring-blue-300 dark:shadow-blue-900/30"
          : status === "completed"
            ? "border-green-200 dark:border-green-800"
            : ""
      }`}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 text-left"
      >
        {expanded ? (
          <ChevronDown className="size-4 shrink-0" />
        ) : (
          <ChevronRight className="size-4 shrink-0" />
        )}
        <StatusIcon status={status} />
        <span className="font-medium">{label}</span>
        {status === "running" && isActive && (
          <span className="ml-1 animate-pulse font-medium text-blue-500 text-sm">
            {CURRENT_STEP_LABELS[name] ?? "分析中..."}
          </span>
        )}
        {status === "running" && !isActive && (
          <span className="text-muted-foreground text-sm">排队中...</span>
        )}
        {status === "completed" && analysisResult?.signal && (
          <span
            className={`ml-1 text-xs ${
              analysisResult.signal === "bullish"
                ? "text-red-500"
                : analysisResult.signal === "bearish"
                  ? "text-green-500"
                  : "text-muted-foreground"
            }`}
          >
            [
            {analysisResult.signal === "bullish"
              ? "看涨"
              : analysisResult.signal === "bearish"
                ? "看跌"
                : "中性"}
            ]
          </span>
        )}
        {status === "failed" && state?.error && (
          <span className="max-w-[200px] truncate text-red-500 text-sm">
            {state.error}
          </span>
        )}
      </button>

      {/* Expandable content */}
      {expanded && (
        <div className="mt-3 max-h-[60vh] overflow-y-auto border-border border-t pt-3">
          {hasSubStates ? (
            <div className="space-y-1">
              {subKeys.map((k) => {
                const subData = state.subStates?.[k];
                return subData != null ? (
                  <SubStateRow key={k} subKey={k} data={subData} />
                ) : (
                  <div
                    key={k}
                    className="mt-1 ml-4 flex items-center gap-1 text-muted-foreground text-sm"
                  >
                    <Circle className="size-3" />
                    <span>
                      {SUB_AGENT_LABEL_ZH[`${name}.${k}`] ?? k}（等待中）
                    </span>
                  </div>
                );
              })}
            </div>
          ) : analysisResult ? (
            <div className="space-y-3">
              <AgentResultDisplay
                result={analysisResult}
                agentName={name}
                showRaw={showRaw}
                onToggleRaw={() => setShowRaw(!showRaw)}
                rawData={state!.output}
              />
            </div>
          ) : state?.output != null ? (
            <pre className="overflow-x-auto whitespace-pre-wrap rounded bg-muted p-2 text-xs">
              {typeof state.output === "string"
                ? state.output
                : JSON.stringify(state.output, null, 2)}
            </pre>
          ) : status === "running" ? (
            <div className="flex items-center gap-2 text-muted-foreground text-sm">
              <Loader2 className="size-3 animate-spin" />
              <span>{CURRENT_STEP_LABELS[name] ?? "正在分析..."}</span>
            </div>
          ) : (
            <p className="text-muted-foreground text-sm">等待分析...</p>
          )}
        </div>
      )}
    </div>
  );
}
