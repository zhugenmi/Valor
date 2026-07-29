import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { usePortfolioStore } from "../store";

const SECTOR_COLORS = [
  "#8884d8",
  "#83a6ed",
  "#8dd1e1",
  "#82ca9d",
  "#a4de6c",
  "#d0ed57",
  "#ffc658",
];

export default function AnalyticsPanel({ pid: _pid }: { pid: string }) {
  // Read from the shared store - the parent detail page already triggered
  // fetchAnalytics on mount, so we must NOT fire a second request here.
  const analytics = usePortfolioStore((s) => s.analytics);
  const loading = usePortfolioStore((s) => s.analyticsLoading);

  if (loading && !analytics) return <div className="p-4">行情计算中...</div>;
  if (!analytics) return <div className="p-4">暂无数据</div>;

  const sectorData = Object.entries(analytics.sector_exposure ?? {}).map(
    ([name, value]) => ({ name, value: value * 100 }),
  );

  return (
    <div className="w-full space-y-4">
      <div className="grid grid-cols-4 gap-3">
        <Card className="p-3">
          <div className="text-gray-500 text-sm">总资产</div>
          <div className="font-bold text-xl">
            ¥
            {Number(analytics.total_assets).toLocaleString(undefined, {
              minimumFractionDigits: 2,
            })}
          </div>
        </Card>
        <Card className="p-3">
          <div className="text-gray-500 text-sm">未实现盈亏</div>
          <div
            className={cn(
              "font-bold text-xl",
              Number(analytics.total_unrealized_pnl) >= 0
                ? "text-red-500"
                : "text-green-500",
            )}
          >
            {Number(analytics.total_unrealized_pnl) >= 0 ? "+" : ""}¥
            {Number(analytics.total_unrealized_pnl).toLocaleString(undefined, {
              minimumFractionDigits: 2,
            })}
            ({(analytics.total_unrealized_pnl_pct * 100).toFixed(2)}%)
          </div>
        </Card>
        <Card className="p-3">
          <div className="text-gray-500 text-sm">组合 Beta</div>
          <div className="font-bold text-xl">
            {analytics.portfolio_beta?.toFixed(2) ?? "-"}
          </div>
        </Card>
        <Card className="p-3">
          <div className="text-gray-500 text-sm">有效持仓</div>
          <div className="font-bold text-xl">
            {analytics.concentration.effective_holdings.toFixed(1)} 只
          </div>
        </Card>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Card className="p-4">
          <div className="mb-2 font-medium">行业暴露</div>
          {sectorData.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={sectorData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  label
                >
                  {sectorData.map((d, i) => (
                    <Cell
                      key={d.name}
                      fill={SECTOR_COLORS[i % SECTOR_COLORS.length]}
                    />
                  ))}
                </Pie>
                <Tooltip formatter={(v) => `${Number(v)?.toFixed(2) ?? ""}%`} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-gray-500 text-sm">暂无行业数据</div>
          )}
        </Card>
        <Card className="p-4">
          <div className="mb-2 font-medium">集中度</div>
          <div className="space-y-1 text-sm">
            <div className="flex justify-between">
              <span>Top1 权重</span>
              <span>
                {(analytics.concentration.top1_weight * 100).toFixed(2)}%
              </span>
            </div>
            <div className="flex justify-between">
              <span>Top5 权重</span>
              <span>
                {(analytics.concentration.top5_weight * 100).toFixed(2)}%
              </span>
            </div>
            <div className="flex justify-between">
              <span>HHI 指数</span>
              <span>{analytics.concentration.herfindahl_index.toFixed(4)}</span>
            </div>
            <div className="flex justify-between">
              <span>持仓数</span>
              <span>{analytics.concentration.num_holdings}</span>
            </div>
          </div>
        </Card>
      </div>
      <Card className="p-4">
        <div className="mb-2 font-medium">持仓明细</div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500">
              <th>代码</th>
              <th>名称</th>
              <th className="text-right">持仓</th>
              <th className="text-right">现价</th>
              <th className="text-right">市值</th>
              <th className="text-right">盈亏</th>
              <th className="text-right">权重</th>
              <th>行业</th>
            </tr>
          </thead>
          <tbody>
            {analytics.positions.map((p) => (
              <tr key={p.ticker} className="border-t">
                <td className="font-mono">{p.ticker}</td>
                <td>{p.name || "-"}</td>
                <td className="text-right">{p.quantity}</td>
                <td className="text-right">
                  ¥{Number(p.current_price).toFixed(2)}
                </td>
                <td className="text-right">
                  ¥{Number(p.market_value).toLocaleString()}
                </td>
                <td
                  className={cn(
                    "text-right",
                    Number(p.unrealized_pnl) >= 0
                      ? "text-red-500"
                      : "text-green-500",
                  )}
                >
                  {Number(p.unrealized_pnl) >= 0 ? "+" : ""}¥
                  {Number(p.unrealized_pnl).toFixed(2)}
                </td>
                <td className="text-right">{(p.weight * 100).toFixed(2)}%</td>
                <td>{p.sector || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
