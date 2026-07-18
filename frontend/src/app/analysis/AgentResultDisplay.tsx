import { useState } from "react";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, CheckCircle2, XCircle, Info, ChevronDown } from "lucide-react";
import type { AnalysisResult, SubSignal, MetricGroup } from "./analysisExtractor";

interface AgentResultDisplayProps {
  result: AnalysisResult;
  agentName: string;
  onToggleRaw?: () => void;
  showRaw?: boolean;
  rawData?: unknown;
}

const SIGNAL_COLORS: Record<string, { bg: string; text: string; icon: typeof CheckCircle2 }> = {
  bullish: { bg: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400", text: "看涨", icon: CheckCircle2 },
  bearish: { bg: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400", text: "看跌", icon: XCircle },
  neutral: { bg: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300", text: "中性", icon: Info },
};

function ConfidenceBar({ value }: { value: number | string | undefined }) {
  if (value === undefined || value === "N/A") {
    return <span className="text-muted-foreground text-xs">置信度: N/A</span>;
  }
  const num = typeof value === "string" ? parseFloat(value) : value;
  const pct = num <= 1 ? num * 100 : num;
  return (
    <div className="max-w-xs w-full">
      <div className="flex items-center justify-between mb-1 text-xs">
        <span>置信度</span>
        <span className="font-medium">{pct.toFixed(0)}%</span>
      </div>
      <Progress className="h-2" value={Math.min(100, Math.max(0, pct))} />
    </div>
  );
}

function MetricRow({ label, value }: { label: string; value: unknown }) {
  if (value === undefined || value === null || value === "") return null;
  let str: string;
  if (typeof value === "object") {
    try { str = JSON.stringify(value); } catch { str = String(value); }
  } else if (typeof value === "number") {
    str = Number.isInteger(value)
      ? String(value)
      : value.toLocaleString(undefined, { maximumFractionDigits: 4 });
  } else {
    str = String(value);
  }
  if (str.length > 200) return null;
  return (
    <div className="border-b border-border/50 flex gap-2 last:border-0 py-1">
      <span className="shrink-0 text-muted-foreground text-xs w-28">{label}</span>
      <span className="break-all font-mono text-foreground text-xs">{str}</span>
    </div>
  );
}

function MetricGroupDisplay({ group, defaultOpen = true }: { group: MetricGroup; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="cursor-pointer flex gap-1 items-center text-muted-foreground text-sm"
      >
        <ChevronDown className={`size-3 transition-transform ${open ? "rotate-90" : ""}`} />
        <span>{group.label}</span>
      </button>
      {open && (
        <div className="mt-1 space-y-0.5">
          {group.rows.map((row, i) => (
            <MetricRow key={`${group.label}-${row.label}-${i}`} label={row.label} value={row.value} />
          ))}
        </div>
      )}
    </div>
  );
}

function RiskFlags({ flags }: { flags: string[] }) {
  if (!flags.length) return null;
  return (
    <div className="mt-3 space-y-1">
      <div className="text-muted-foreground text-xs font-medium">风险标记</div>
      <div className="flex flex-wrap gap-1">
        {flags.map((flag, i) => (
          <Badge key={`${flag}-${i}`} variant="destructive" className="gap-1 text-xs">
            <AlertTriangle className="size-2.5" />
            {flag}
          </Badge>
        ))}
      </div>
    </div>
  );
}

function SubSignalRow({ sub, index }: { sub: SubSignal; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const signalInfo = sub.signal ? SIGNAL_COLORS[sub.signal] : null;
  const hasMetrics = sub.metrics && Object.keys(sub.metrics).length > 0;

  return (
    <div className="border-b border-border/40 last:border-0 py-1.5">
      <div className="flex flex-wrap gap-2 items-center">
        <span className="font-medium text-sm">{sub.label}</span>
        {signalInfo && (
          <Badge className={`${signalInfo.bg} text-xs`} variant="outline">
            <signalInfo.icon className="size-2.5" />
            {signalInfo.text}
          </Badge>
        )}
        {sub.confidence !== undefined && (
          <span className="text-muted-foreground text-xs">
            置信度 {typeof sub.confidence === "number"
              ? `${Math.round((sub.confidence <= 1 ? sub.confidence * 100 : sub.confidence))}%`
              : sub.confidence}
          </span>
        )}
        {hasMetrics && (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="flex gap-0.5 items-center text-muted-foreground hover:text-foreground text-xs transition-colors"
          >
            <ChevronDown className={`size-3 transition-transform ${expanded ? "rotate-90" : ""}`} />
            指标
          </button>
        )}
      </div>
      {sub.details && (
        <p className="mt-1 text-muted-foreground text-xs">{sub.details}</p>
      )}
      {expanded && hasMetrics && (
        <div className="mt-1 space-y-0.5">
          {Object.entries(sub.metrics!).map(([k, v]) => (
            <MetricRow key={`${sub.label}-${k}-${index}`} label={k} value={v} />
          ))}
        </div>
      )}
    </div>
  );
}

function SubSignals({ subSignals }: { subSignals: SubSignal[] }) {
  if (!subSignals.length) return null;
  return (
    <details className="group" open>
      <summary className="cursor-pointer flex gap-1 items-center text-muted-foreground text-sm">
        <span>分项信号</span>
        <ChevronDown className="size-3 transition-transform group-open:rotate-90" />
      </summary>
      <div className="mt-1">
        {subSignals.map((sub, i) => (
          <SubSignalRow key={`${sub.label}-${i}`} sub={sub} index={i} />
        ))}
      </div>
    </details>
  );
}

export default function AgentResultDisplay({
  result,
  agentName,
  onToggleRaw,
  showRaw,
  rawData,
}: AgentResultDisplayProps) {
  const signalInfo = result.signal ? SIGNAL_COLORS[result.signal] : null;

  return (
    <div className="space-y-3">
      {signalInfo && (
        <div className="flex flex-wrap gap-2 items-center">
          <Badge className={signalInfo.bg} variant="outline">
            <signalInfo.icon className="size-3" />
            {signalInfo.text}
          </Badge>
          <ConfidenceBar value={result.confidence} />
        </div>
      )}

      {result.reasoning && (
        <div className="prose dark:prose-invert max-w-none prose-sm">
          <p className="whitespace-pre-wrap text-sm">{result.reasoning}</p>
        </div>
      )}

      {result.subSignals && result.subSignals.length > 0 && (
        <SubSignals subSignals={result.subSignals} />
      )}

      {result.metricGroups && result.metricGroups.length > 0 && (
        <div className="space-y-2">
          {result.metricGroups.map((group, i) => (
            <MetricGroupDisplay key={`group-${i}`} group={group} defaultOpen={i === 0} />
          ))}
        </div>
      )}

      {result.metrics && Object.keys(result.metrics).length > 0 && (
        <details className="group">
          <summary className="cursor-pointer flex gap-1 items-center text-muted-foreground text-sm">
            <span>关键指标</span>
            <ChevronDown className="size-3 transition-transform group-open:rotate-90" />
          </summary>
          <div className="mt-2 space-y-1 text-xs">
            {Object.entries(result.metrics).map(([key, value]) => (
              <MetricRow key={key} label={key} value={value} />
            ))}
          </div>
        </details>
      )}

      <RiskFlags flags={result.riskFlags ?? []} />

      {onToggleRaw && (
        <button
          type="button"
          onClick={onToggleRaw}
          className="flex gap-1 items-center text-muted-foreground hover:text-foreground text-xs transition-colors"
        >
          {showRaw ? "隐藏原始数据" : "查看原始数据"}
          <ChevronDown className="size-3 transition-transform" />
        </button>
      )}

      {showRaw && rawData != null && (
        <pre className="bg-muted max-h-60 overflow-auto p-2 rounded text-xs mt-2">
          {typeof rawData === "string" ? rawData : JSON.stringify(rawData, null, 2)}
        </pre>
      )}
    </div>
  );
}