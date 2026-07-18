import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { portfolioApi, type StrategyRequest } from "@/api/portfolio";
import { usePortfolioStore } from "../store";

interface Props { pid: string; defaultTickers: string[]; }

export default function AllocatorRunner({ pid, defaultTickers }: Props) {
  const fetchDetail = usePortfolioStore((s) => s.fetchDetail);
  const [method, setMethod] = useState<StrategyRequest["method"]>("equal_weight");
  const [tickersText, setTickersText] = useState(defaultTickers.join(","));
  const [maxWeight, setMaxWeight] = useState("0.40");
  const [lookback, setLookback] = useState("252");
  const [running, setRunning] = useState(false);

  async function run() {
    const tickers = tickersText.split(",").map((t) => t.trim()).filter(Boolean);
    if (tickers.length === 0) return;
    setRunning(true);
    try {
      await portfolioApi.createStrategy(pid, {
        method, tickers,
        params: { max_weight: Number(maxWeight), lookback_days: Number(lookback) },
      });
      await fetchDetail(pid);
    } catch (e) {
      alert(`运行失败：${(e as Error).message}`);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-3 rounded border p-4">
      <div className="font-medium">运行新 Allocator</div>
      <div>
        <Label>方法</Label>
        <select className="w-full rounded border px-2 py-1" value={method} onChange={(e) => setMethod(e.target.value as StrategyRequest["method"])}>
          <option value="equal_weight">等权（equal_weight）</option>
          <option value="mean_variance">均值方差（mean_variance）</option>
          <option value="risk_parity">风险平价（risk_parity）</option>
        </select>
      </div>
      <div><Label>标的（逗号分隔）</Label>
        <input className="w-full rounded border px-2 py-1" value={tickersText} onChange={(e) => setTickersText(e.target.value)} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div><Label>最大权重</Label><input className="w-full rounded border px-2 py-1" value={maxWeight} onChange={(e) => setMaxWeight(e.target.value)} /></div>
        <div><Label>回看天数</Label><input className="w-full rounded border px-2 py-1" value={lookback} onChange={(e) => setLookback(e.target.value)} /></div>
      </div>
      <Button onClick={run} disabled={running}>{running ? "运行中..." : "运行"}</Button>
    </div>
  );
}