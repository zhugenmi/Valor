import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { formatMoney, formatPercent, formatPnlClass } from "@/lib/format";
import PortfolioForm from "./components/PortfolioForm";
import { usePortfolioStore } from "./store";

export default function PortfolioListPage() {
  const navigate = useNavigate();
  const { list, loading, error, fetchList, remove } = usePortfolioStore();
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  return (
    <div className="w-full px-6 py-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="font-bold text-2xl">我的组合</h1>
        <Button onClick={() => setShowForm(true)}>
          <Plus className="mr-1 h-4 w-4" /> 新建
        </Button>
      </div>
      {error && <div className="mb-4 text-red-500">{error}</div>}
      {loading && <div className="text-gray-500">加载中...</div>}
      <div className="mx-auto max-w-4xl">
        <div className="space-y-3">
          {list.map((p) => {
            const hasAnalytics = p.total_market_value != null;
            const mv = Number(p.total_market_value ?? 0);
            const pnl = Number(p.total_unrealized_pnl ?? 0);
            const pnlPct = p.total_unrealized_pnl_pct ?? 0;
            return (
              <Card
                className="flex cursor-pointer items-stretch justify-between p-0 hover:shadow-md"
                key={p.portfolio_id}
                onClick={() => navigate(`/portfolio/${p.portfolio_id}`)}
              >
                <div className="flex flex-1 flex-col gap-0.5 p-4">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-lg">{p.name}</span>
                    {p.num_holdings != null && (
                      <span className="rounded bg-muted px-1.5 py-0.5 text-muted-foreground text-xs">
                        {p.num_holdings} 只
                      </span>
                    )}
                  </div>
                  {hasAnalytics && mv > 0 ? (
                    <div className="mt-1 space-y-0.5">
                      <div className="font-semibold text-xl tracking-tight">
                        {formatMoney(mv)}
                      </div>
                      <div className={`text-sm ${formatPnlClass(pnl)}`}>
                        {pnl >= 0 ? "+" : ""}
                        {formatMoney(Math.abs(pnl))} ({formatPercent(pnlPct)}){" "}
                        <span className="font-normal text-muted-foreground">
                          浮动盈亏
                        </span>
                      </div>
                    </div>
                  ) : (
                    <div className="mt-2 text-muted-foreground text-sm">
                      暂无市场数据
                    </div>
                  )}
                  <div className="mt-auto text-muted-foreground text-xs">
                    基准 {p.benchmark} · 现金 {formatMoney(p.cash)} · 更新{" "}
                    {new Date(p.updated_at).toLocaleString()}
                  </div>
                </div>
                <div className="flex items-start p-2">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="mt-2"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm(`删除组合「${p.name}」？`))
                        remove(p.portfolio_id);
                    }}
                  >
                    <Trash2 className="h-4 w-4 text-red-500" />
                  </Button>
                </div>
              </Card>
            );
          })}
          {!loading && list.length === 0 && (
            <div className="py-12 text-center text-gray-500">
              暂无组合，点击「新建」开始
            </div>
          )}
        </div>
      </div>
      <PortfolioForm
        onClose={() => setShowForm(false)}
        onCreated={(id) => navigate(`/portfolio/${id}`)}
        open={showForm}
      />
    </div>
  );
}
