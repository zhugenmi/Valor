import type { Decision } from "./constants";

interface DecisionPanelProps {
  decision: Decision | null;
}

const ACTION_LABEL_ZH: Record<Decision["action"], string> = {
  buy: "买入",
  sell: "卖出",
  hold: "持有",
};

const ACTION_COLOR: Record<Decision["action"], string> = {
  buy: "text-red-500",
  sell: "text-green-500",
  hold: "text-muted-foreground",
};

export default function DecisionPanel({ decision }: DecisionPanelProps) {
  if (!decision) {
    return null;
  }

  // When action is "hold" and current position is 0, the user is on the
  // sidelines - display "观望" (wait-and-see) rather than "持有" (hold existing).
  const currentPosition = decision.current_position ?? 0;
  const isWatching = decision.action === "hold" && currentPosition === 0;
  const actionLabel = isWatching ? "观望" : ACTION_LABEL_ZH[decision.action];
  const actionColor = isWatching ? "text-muted-foreground" : ACTION_COLOR[decision.action];

  return (
    <div className="rounded-lg border-2 border-primary bg-card p-4">
      <h2 className="mb-3 font-semibold text-lg">最终决策</h2>
      <div className="mb-3 flex items-center gap-4">
        <span className={`font-bold text-2xl ${actionColor}`}>
          {actionLabel}
        </span>
        {decision.action !== "hold" && (
          <span className="text-lg">{decision.quantity} 股</span>
        )}
        <span className="text-muted-foreground">
          置信度: {(decision.confidence * 100).toFixed(0)}%
        </span>
      </div>
      {decision.reasoning && (
        <details>
          <summary className="cursor-pointer text-muted-foreground text-sm">推理过程</summary>
          <p className="mt-2 whitespace-pre-wrap text-sm">{decision.reasoning}</p>
        </details>
      )}
    </div>
  );
}