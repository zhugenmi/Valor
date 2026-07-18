import { AGENT_ORDER, AGENT_LABEL_SHORT_ZH } from "./constants";

interface ProgressBarProps {
  currentAgent: string | null;
  completedAgents: string[];
}

export default function ProgressBar({ currentAgent, completedAgents }: ProgressBarProps) {
  return (
    <div className="bg-card border p-4 rounded-lg">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-sm">分析进度</h3>
        <span className="text-muted-foreground text-xs">
          {completedAgents.length} / {AGENT_ORDER.length} 完成
        </span>
      </div>
      <div className="flex flex-wrap gap-1.5 items-center">
        {AGENT_ORDER.map((agentName, index) => {
          const isCompleted = completedAgents.includes(agentName);
          const isCurrent = currentAgent === agentName;
          const label = AGENT_LABEL_SHORT_ZH[agentName] ?? agentName;

          return (
            <div
              key={agentName}
              className={`duration-300 flex flex-col gap-1 items-center relative transition-all ${isCurrent ? "scale-105" : ""}`}
            >
              <div
                className={`duration-300 flex h-10 items-center justify-center relative rounded-full transition-all w-10 ${
                  isCompleted
                    ? "bg-green-500 text-white"
                    : isCurrent
                    ? "animate-pulse bg-blue-500 ring-2 ring-blue-500/30 text-white"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {isCompleted ? (
                  <svg className="size-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                  </svg>
                ) : isCurrent ? (
                  <div className="animate-pulse bg-white rounded-full size-2" />
                ) : (
                  <div className="bg-transparent ring-1 ring-current rounded-full size-2" />
                )}
              </div>
              <span
                className={`font-medium text-center text-xs transition-colors whitespace-nowrap ${
                  isCompleted
                    ? "text-green-600"
                    : isCurrent
                    ? "text-blue-600"
                    : "text-muted-foreground"
                }`}
              >
                {label}
              </span>
              {index < AGENT_ORDER.length - 1 && (
                <div
                  className={`absolute left-full top-1/2 -translate-y-1/2 h-0.5 transition-colors w-8 ${
                    isCompleted || isCurrent ? "bg-green-500" : "bg-border"
                  }`}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}