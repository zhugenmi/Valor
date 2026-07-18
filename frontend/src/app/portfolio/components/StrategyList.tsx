import { useState } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { usePortfolioStore } from "../store";
import { portfolioApi } from "@/api/portfolio";
import AllocatorRunner from "./AllocatorRunner";

interface Props { pid: string; }

export default function StrategyList({ pid }: Props) {
  const { current, fetchDetail } = usePortfolioStore();
  const [selected, setSelected] = useState<Set<string>>(new Set());

  if (!current) return null;

  async function remove(sid: string) {
    if (!confirm("删除该策略？")) return;
    await portfolioApi.deleteStrategy(pid, sid);
    await fetchDetail(pid);
  }

  function toggle(sid: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(sid)) next.delete(sid);
      else next.add(sid);
      return next;
    });
  }

  const defaultTickers = current.holdings.map((h) => h.ticker);

  return (
    <div className="space-y-4">
      <AllocatorRunner pid={pid} defaultTickers={defaultTickers} />
      <Card className="p-4">
        <div className="mb-2 font-medium">已保存策略</div>
        {current.strategies.length === 0 ? (
          <div className="text-gray-500 text-sm">暂无策略，运行上方 Allocator 生成</div>
        ) : (
          <table className="w-full text-sm">
            <thead><tr className="text-left text-gray-500">
              <th></th><th>名称</th><th>方法</th><th className="text-right">期望收益</th>
              <th className="text-right">波动率</th><th>创建时间</th><th></th>
            </tr></thead>
            <tbody>
              {current.strategies.map((s) => (
                <tr key={s.strategy_id} className="border-t">
                  <td><input type="checkbox" checked={selected.has(s.strategy_id)} onChange={() => toggle(s.strategy_id)} /></td>
                  <td>{s.name}</td>
                  <td className="font-mono">{s.method}</td>
                  <td className="text-right">{s.expected_return != null ? `${(s.expected_return * 100).toFixed(2)}%` : "-"}</td>
                  <td className="text-right">{s.expected_volatility != null ? `${(s.expected_volatility * 100).toFixed(2)}%` : "-"}</td>
                  <td>{new Date(s.created_at).toLocaleString()}</td>
                  <td><Button variant="ghost" size="icon" onClick={() => remove(s.strategy_id)}><Trash2 className="h-4 w-4 text-red-500" /></Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {selected.size >= 2 && (
        <Card className="p-4">
          <div className="mb-2 font-medium">策略对比</div>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-gray-500"><th>Ticker</th>
              {current.strategies.filter((s) => selected.has(s.strategy_id)).map((s) => <th key={s.strategy_id}>{s.name}</th>)}
            </tr></thead>
            <tbody>
              {Array.from(new Set(current.strategies.filter((s) => selected.has(s.strategy_id)).flatMap((s) => Object.keys(s.target_weights)))).map((t) => (
                <tr key={t} className="border-t">
                  <td className="font-mono">{t}</td>
                  {current.strategies.filter((s) => selected.has(s.strategy_id)).map((s) => (
                    <td key={s.strategy_id} className="text-right">{((s.target_weights[t] || 0) * 100).toFixed(2)}%</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}