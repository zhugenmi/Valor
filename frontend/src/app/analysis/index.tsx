import { useState, useEffect } from "react";
import { Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useStreamAnalysis } from "@/api/analysis";
import {
  AGENT_ORDER,
  SUB_AGENT_KEYS,
  type AgentState,
  type Decision,
} from "./constants";
import AgentCard from "./AgentCard";
import DecisionPanel from "./DecisionPanel";
import AdvancedParams, {
  type AdvancedParamsValue,
  defaultAnalysisDates,
} from "./AdvancedParams";
import ProgressBar from "./ProgressBar";

function initPendingAgents(): Record<string, AgentState> {
  const agents: Record<string, AgentState> = {};
  for (const name of AGENT_ORDER) {
    agents[name] = { status: "pending", output: null };
  }
  return agents;
}

/**
 * Determine which agent should be running based on completed agents' status.
 * Returns the first agent that is pending OR running (running covers
 * bull_bear_debate while its sub-stages are still streaming in).
 */
function calcCurrentAgent(
  agents: Record<string, AgentState>,
): string | null {
  for (const name of AGENT_ORDER) {
    const s = agents[name];
    if (!s || s.status === "pending") return name;
    if (s.status === "running") return name;
  }
  return null;
}

export default function AnalysisPage() {
  const [ticker, setTicker] = useState("");
  const [advanced, setAdvanced] = useState<AdvancedParamsValue>(
    defaultAnalysisDates(),
  );
  const [agents, setAgents] = useState<Record<string, AgentState>>({});
  const [decision, setDecision] = useState<Decision | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [currentAgent, setCurrentAgent] = useState<string | null>(null);

  // Derive current agent whenever agents state changes
  useEffect(() => {
    if (!streaming) return;
    setCurrentAgent(calcCurrentAgent(agents));
  }, [agents, streaming]);

  const { startStream } = useStreamAnalysis({
    onWorkflowStarted: () => {
      setAgents(initPendingAgents());
      setDecision(null);
    },
    onAgentCompleted: (data) => {
      const dotIdx = data.agent.indexOf(".");
      if (dotIdx > 0) {
        // bull_bear_debate.bull / .bear / .verdict
        const parent = data.agent.slice(0, dotIdx);
        const sub = data.agent.slice(dotIdx + 1);
        setAgents((prev) => {
          const current = prev[parent] ?? { status: "running" as const, output: null };
          const subStates = { ...(current.subStates ?? {}), [sub]: data.state };
          const allSubs = SUB_AGENT_KEYS[parent] ?? [];
          const allDone = allSubs.every((k) => k in subStates);
          return {
            ...prev,
            [parent]: {
              ...current,
              status: allDone ? "completed" : "running",
              subStates,
            },
          };
        });
      } else {
        setAgents((prev) => ({
          ...prev,
          [data.agent]: { status: "completed", output: data.state },
        }));
      }
    },
    onWorkflowCompleted: (data) => {
      setDecision(data.final_decision);
      setStreaming(false);
      setCurrentAgent(null);
    },
    onSystemFailed: (data) => {
      setStreaming(false);
      setCurrentAgent(null);
      console.error("分析失败:", data.payload.content);
    },
  });

  const handleAnalyze = async () => {
    if (!ticker.trim()) return;
    setStreaming(true);
    setAgents(initPendingAgents());
    setDecision(null);
    setCurrentAgent(AGENT_ORDER[0]);
    await startStream({
      ticker: ticker.trim(),
      startDate: advanced.startDate || undefined,
      endDate: advanced.endDate || undefined,
    });
  };

  const completedAgents = AGENT_ORDER.filter(
    (name) => agents[name]?.status === "completed",
  );

  return (
    <div className="mx-auto flex h-full w-full max-w-7xl flex-col gap-4 overflow-y-auto px-6 py-4">
      <div className="flex gap-2">
        <input
          type="text"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          placeholder="输入股票代码，如 600519"
          className="flex-1 rounded border p-2"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !streaming) handleAnalyze();
          }}
        />
        <Button onClick={handleAnalyze} disabled={streaming || !ticker.trim()}>
          <Play className="mr-1 size-4" />
          {streaming ? "分析中..." : "分析"}
        </Button>
      </div>

      <AdvancedParams value={advanced} onChange={setAdvanced} />

      {streaming && (
        <ProgressBar
          currentAgent={currentAgent}
          completedAgents={completedAgents}
        />
      )}

      <div className="flex flex-col gap-2">
        {AGENT_ORDER.map((name) => (
          <AgentCard
            key={name}
            name={name}
            state={agents[name]}
            isActive={currentAgent === name}
          />
        ))}
      </div>

      <DecisionPanel decision={decision} />
    </div>
  );
}