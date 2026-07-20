import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { useState, type FC } from "react";
import {
  AGENT_ORDER,
  type AgentState,
  type Decision,
  SUB_AGENT_KEYS,
} from "@/app/analysis/components/constants";
import AgentCard from "@/app/analysis/components/AgentCard";
import DecisionPanel from "@/app/analysis/components/DecisionPanel";
import ProgressBar from "@/app/analysis/components/ProgressBar";

interface DiagnosisSectionContent {
  ticker: string;
  agents: Record<string, AgentState>;
  decision: Decision | null;
  preflight: { trading_day: string; filled: boolean } | null;
  currentAgent: string | null;
}

interface DiagnosisSectionRendererProps {
  content: string;
}

const DiagnosisSectionRenderer: FC<DiagnosisSectionRendererProps> = ({ content }) => {
  const [collapsed, setCollapsed] = useState(false);
  let parsed: DiagnosisSectionContent;
  try {
    parsed = JSON.parse(content) as DiagnosisSectionContent;
  } catch {
    return null;
  }

  const completedAgents = AGENT_ORDER.filter(
    (name) => parsed.agents[name]?.status === "completed",
  );
  const isStreaming = parsed.currentAgent !== null;

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700">
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        className="flex w-full items-center justify-between p-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800"
      >
        <div className="flex items-center gap-2">
          {collapsed ? (
            <ChevronRight className="size-4" />
          ) : (
            <ChevronDown className="size-4" />
          )}
          <span className="font-medium">
            股票诊断 · {parsed.ticker}
          </span>
          {parsed.preflight && (
            <span className="text-xs text-gray-500">
              数据日: {parsed.preflight.trading_day}
              {parsed.preflight.filled ? "（已补齐）" : ""}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          {isStreaming && <Loader2 className="size-3 animate-spin" />}
          <span>
            {completedAgents.length}/{AGENT_ORDER.length}
          </span>
        </div>
      </button>

      {!collapsed && (
        <div className="border-t border-gray-200 p-3 dark:border-gray-700">
          {isStreaming && (
            <ProgressBar
              currentAgent={parsed.currentAgent}
              completedAgents={completedAgents}
            />
          )}
          <div className="mt-2 flex flex-col gap-2">
            {AGENT_ORDER.map((name) => (
              <AgentCard
                key={name}
                name={name}
                state={parsed.agents[name]}
                isActive={parsed.currentAgent === name}
              />
            ))}
          </div>
          <DecisionPanel decision={parsed.decision} />
        </div>
      )}
    </div>
  );
};

export default DiagnosisSectionRenderer;
