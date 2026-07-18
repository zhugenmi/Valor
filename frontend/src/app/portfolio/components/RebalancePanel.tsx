import { useState } from "react";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { usePortfolioStore } from "../store";
import { portfolioApi } from "@/api/portfolio";
import type { RebalancePlan } from "../types";

export default function RebalancePanel({ pid }: { pid: string }) {
  const { current } = usePortfolioStore();
  const [selectedStrategy, setSelectedStrategy] = useState("");
  const [plan, setPlan] = useState<RebalancePlan | null>(null);
  const [running, setRunning] = useState(false);

  async function run() {
    if (!selectedStrategy) return;
    setRunning(true);
    try {
      const p = await portfolioApi.rebalance(pid, selectedStrategy);
      setPlan(p);
    } catch (e) {
      alert(`生成失败：${(e as Error).message}`);
    } finally {
      setRunning(false);
    }
  }

  function exportCsv() {
    if (!plan) return;
    const rows = [["ticker", "side", "delta_quantity", "target_quantity", "target_weight", "current_weight", "est_cost", "rationale"]];
    for (const a of plan.actions) {
      rows.push([
        a.ticker, a.side, String(a.delta_quantity), String(a.target_quantity),
        String(a.target_weight), String(a.current_weight), a.est_cost, a.rationale,
      ]);
    }
    const csv = rows.map((r) => r.map((c) => `"${c}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `rebalance_${pid}_${plan.strategy_id}.csv`; a.click();
    URL.revokeObjectURL(url);
  }

  if (!current) return null;

  return (
    <div className="space-y-4">
      <Card className={cn("flex items-end gap-2 p-4")}>
        <div className="flex-1">
          <label htmlFor="strategy-select" className="text-sm">基于策略</label>
          <select id="strategy-select" className={cn("w-full rounded border px-2 py-1")} value={selectedStrategy} onChange={(e) => setSelectedStrategy(e.target.value)}>
            <option value="">请选择...</option>
            {current.strategies.map((s) => <option key={s.strategy_id} value={s.strategy_id}>{s.name}</option>)}
          </select>
        </div>
        <Button onClick={run} disabled={running || !selectedStrategy}>{running ? "生成中..." : "生成调仓建议"}</Button>
      </Card>
      {plan && (
        <>
          {plan.warnings.length > 0 && (
            <Card className={cn("border-yellow-200 bg-yellow-50 p-3")}>
              {plan.warnings.map((w) => <div key={w} className="text-sm text-yellow-800">⚠ {w}</div>)}
            </Card>
          )}
          {plan.fund_transfers.length > 0 && (
            <Card className={cn("border-blue-200 bg-blue-50 p-3")}>
              <div className="mb-1 font-medium text-blue-900">跨组合资金调拨建议</div>
              {plan.fund_transfers.map((ft) => (
                <div key={`${ft.from_portfolio_id}-${ft.to_portfolio_id}-${ft.amount}`} className="text-blue-800 text-sm">¥{Number(ft.amount).toLocaleString()}：{ft.rationale}</div>
              ))}
            </Card>
          )}
          <Card className="p-4">
            <div className={cn("mb-2 flex items-center justify-between")}>
              <div className="font-medium">调仓明细</div>
              <Button variant="outline" size="sm" onClick={exportCsv}><Download className={cn("mr-1 h-4 w-4")} /> 导出 CSV</Button>
            </div>
            <table className="w-full text-sm">
              <thead><tr className="text-left text-gray-500">
                <th>代码</th><th>方向</th><th className="text-right">调整量</th>
                <th className="text-right">目标量</th><th className="text-right">目标权重</th>
                <th className="text-right">当前权重</th><th className="text-right">成本</th><th>理由</th>
              </tr></thead>
              <tbody>
                {plan.actions.map((a) => (
                  <tr key={a.ticker} className="border-t">
                    <td className="font-mono">{a.ticker}</td>
                    <td className={cn(a.side === "buy" ? "text-red-500" : "text-green-500")}>
                      {a.side === "buy" ? "买入" : "卖出"}
                    </td>
                    <td className="text-right">{a.delta_quantity > 0 ? "+" : ""}{a.delta_quantity}</td>
                    <td className="text-right">{a.target_quantity}</td>
                    <td className="text-right">{(a.target_weight * 100).toFixed(2)}%</td>
                    <td className="text-right">{(a.current_weight * 100).toFixed(2)}%</td>
                    <td className="text-right">¥{Number(a.est_cost).toFixed(2)}</td>
                    <td className="text-gray-500 text-xs">{a.rationale}</td>
                  </tr>
                ))}
                {plan.actions.length === 0 && <tr><td colSpan={8} className="py-4 text-center text-gray-500">无调仓动作</td></tr>}
              </tbody>
            </table>
            <div className={cn("mt-3 space-y-1 border-t pt-3 text-sm")}>
              <div className="flex justify-between"><span>总交易成本</span><span>¥{Number(plan.total_est_cost).toFixed(2)}</span></div>
              <div className="flex justify-between"><span>现金变化</span><span>¥{Number(plan.cash_before).toFixed(2)} → ¥{Number(plan.cash_after).toFixed(2)}</span></div>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}