import { AGENT_LABEL_SHORT_ZH, AGENT_ORDER } from "./constants";

interface ProgressBarProps {
  currentAgent: string | null;
  completedAgents: string[];
}

export default function ProgressBar({
  currentAgent,
  completedAgents,
}: ProgressBarProps) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-semibold text-sm">分析进度</h3>
        <span className="text-muted-foreground text-xs">
          {completedAgents.length} / {AGENT_ORDER.length} 完成
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {AGENT_ORDER.map((agentName, index) => {
          const isCompleted = completedAgents.includes(agentName);
          const isCurrent = currentAgent === agentName;
          const label = AGENT_LABEL_SHORT_ZH[agentName] ?? agentName;

          return (
            <div
              key={agentName}
              className={`relative flex flex-col items-center gap-1 transition-all duration-300 ${isCurrent ? "scale-105" : ""}`}
            >
              <div
                className={`relative flex h-10 w-10 items-center justify-center rounded-full transition-all duration-300 ${
                  isCompleted
                    ? "bg-green-500 text-white"
                    : isCurrent
                      ? "animate-pulse bg-blue-500 text-white ring-2 ring-blue-500/30"
                      : "bg-muted text-muted-foreground"
                }`}
              >
                {isCompleted ? (
                  <svg
                    className="size-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={3}
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                ) : isCurrent ? (
                  <div className="size-2 animate-pulse rounded-full bg-white" />
                ) : (
                  <div className="size-2 rounded-full bg-transparent ring-1 ring-current" />
                )}
              </div>
              <span
                className={`whitespace-nowrap text-center font-medium text-xs transition-colors ${
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
                  className={`absolute top-1/2 left-full h-0.5 w-8 -translate-y-1/2 transition-colors ${
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
