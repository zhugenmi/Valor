import { parse } from "best-effort-json-parser";
import { Minus, TrendingDown, TrendingUp } from "lucide-react";
import { type FC, memo } from "react";
import { cn } from "@/lib/utils";
import type { DecisionPayload } from "@/types/agent";
import type { DecisionRendererProps } from "@/types/renderer";
import MarkdownRenderer from "./markdown-renderer";

const ACTION_CONFIG: Record<
  DecisionPayload["action"],
  {
    label: string;
    icon: typeof TrendingUp;
    textClass: string;
    bgClass: string;
    barClass: string;
  }
> = {
  buy: {
    label: "买入",
    icon: TrendingUp,
    textClass: "text-emerald-600 dark:text-emerald-400",
    bgClass: "bg-emerald-500/10",
    barClass: "bg-emerald-500 dark:bg-emerald-400",
  },
  sell: {
    label: "卖出",
    icon: TrendingDown,
    textClass: "text-rose-600 dark:text-rose-400",
    bgClass: "bg-rose-500/10",
    barClass: "bg-rose-500 dark:bg-rose-400",
  },
  hold: {
    label: "持有",
    icon: Minus,
    textClass: "text-amber-600 dark:text-amber-400",
    bgClass: "bg-amber-500/10",
    barClass: "bg-amber-500 dark:bg-amber-400",
  },
};

const DecisionRenderer: FC<DecisionRendererProps> = ({ content }) => {
  const parsed = parse(content) as DecisionPayload | null;
  if (!parsed || !parsed.action) return null;

  const config = ACTION_CONFIG[parsed.action];
  const ActionIcon = config.icon;
  const quantity = parsed.quantity ?? 0;
  const confidencePct = Math.round(
    Math.min(Math.max(parsed.confidence ?? 0, 0), 1) * 100,
  );

  // quantity semantics differ by action: buy/sell = proposed trade size,
  // hold = current position. hold with 0 shares is "stay flat / watch".
  const quantityLabel = (() => {
    switch (parsed.action) {
      case "buy":
        return `建议买入 ${quantity} 股`;
      case "sell":
        return `建议卖出 ${quantity} 股`;
      case "hold":
        return quantity > 0 ? `当前持仓 ${quantity} 股` : "空仓观望";
    }
  })();

  return (
    <div className="min-w-96 space-y-3 rounded-xl border-gradient p-4">
      <div className="flex items-center gap-3">
        <div
          className={cn(
            "flex size-10 items-center justify-center rounded-xl",
            config.bgClass,
          )}
        >
          <ActionIcon className={cn("size-6", config.textClass)} />
        </div>
        <div className="flex flex-col">
          <p
            className={cn("font-semibold text-lg leading-6", config.textClass)}
          >
            {config.label}
          </p>
          <p className="text-muted-foreground text-xs leading-4">
            {quantityLabel}
          </p>
        </div>
      </div>

      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">信心度</span>
          <span className="font-medium text-foreground">{confidencePct}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
          <div
            className={cn("h-full rounded-full", config.barClass)}
            style={{ width: `${confidencePct}%` }}
          />
        </div>
      </div>

      {parsed.reasoning && (
        <div className="border-t pt-2">
          <MarkdownRenderer
            content={parsed.reasoning}
            className="text-muted-foreground text-sm"
          />
        </div>
      )}
    </div>
  );
};

export default memo(DecisionRenderer);
