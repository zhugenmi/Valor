import { Plus, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import AnalyticsPanel from "./components/AnalyticsPanel";
import CSVImport from "./components/CSVImport";
import EditLotForm from "./components/EditLotForm";
import HoldingForm from "./components/HoldingForm";
import HoldingsTable from "./components/HoldingsTable";
import ReduceForm from "./components/ReduceForm";
import RebalancePanel from "./components/RebalancePanel";
import StrategyList from "./components/StrategyList";
import { usePortfolioStore } from "./store";
import type { Lot } from "./types";

export default function PortfolioDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { current, fetchDetail, fetchAnalytics, analyticsLoading } =
    usePortfolioStore();
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [appendTarget, setAppendTarget] = useState<{
    ticker: string;
    name: string | null;
  } | null>(null);
  const [reduceTarget, setReduceTarget] = useState<{
    ticker: string;
    name: string | null;
    maxQty: number;
  } | null>(null);
  const [editLotTarget, setEditLotTarget] = useState<{
    ticker: string;
    lot: Lot;
  } | null>(null);

  useEffect(() => {
    if (id) fetchDetail(id);
  }, [id, fetchDetail]);

  if (!current || !id) return <div className="p-6">加载中...</div>;

  function qtyOf(ticker: string): number {
    const h = current?.holdings.find((x) => x.ticker === ticker);
    if (!h) return 0;
    return h.lots.reduce((s, l) => s + l.quantity, 0);
  }

  return (
    <div className={cn("mx-auto max-w-6xl p-6")}>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-bold text-2xl">{current.name}</h1>
          <div className="text-gray-500 text-sm">
            基准 {current.benchmark} · 现金 ¥
            {Number(current.cash).toLocaleString()} · 持仓{" "}
            {current.holdings.length} 只
          </div>
        </div>
      </div>
      <Tabs defaultValue="holdings">
        <TabsList>
          <TabsTrigger value="holdings">持仓</TabsTrigger>
          <TabsTrigger value="analytics">分析</TabsTrigger>
          <TabsTrigger value="strategies">策略</TabsTrigger>
          <TabsTrigger value="rebalance">调仓</TabsTrigger>
        </TabsList>
        <TabsContent value="holdings" className="space-y-4">
          <div className="flex justify-end gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => id && fetchAnalytics(id)}
              disabled={analyticsLoading}
            >
              <RefreshCw
                className={cn("mr-1 h-4 w-4", analyticsLoading && "animate-spin")}
              />
              {analyticsLoading ? "刷新中..." : "刷新行情"}
            </Button>
            <CSVImport pid={id} />
            <Button size="sm" onClick={() => setShowCreateForm(true)}>
              <Plus className={cn("mr-1 h-4 w-4")} /> 新增持仓
            </Button>
          </div>
          <HoldingsTable
            pid={id}
            holdings={current.holdings}
            onAppend={(ticker, name) => setAppendTarget({ ticker, name })}
            onReduce={(ticker, name) =>
              setReduceTarget({ ticker, name, maxQty: qtyOf(ticker) })
            }
            onEditLot={(ticker, lot) => setEditLotTarget({ ticker, lot })}
          />
          <HoldingForm
            pid={id}
            open={showCreateForm}
            onClose={() => setShowCreateForm(false)}
            mode="create"
          />
          <HoldingForm
            pid={id}
            open={appendTarget !== null}
            onClose={() => setAppendTarget(null)}
            mode="append"
            ticker={appendTarget?.ticker}
            name={appendTarget?.name}
          />
          <ReduceForm
            pid={id}
            open={reduceTarget !== null}
            onClose={() => setReduceTarget(null)}
            ticker={reduceTarget?.ticker ?? ""}
            name={reduceTarget?.name}
            maxQuantity={reduceTarget?.maxQty ?? 0}
          />
          <EditLotForm
            pid={id}
            open={editLotTarget !== null}
            onClose={() => setEditLotTarget(null)}
            ticker={editLotTarget?.ticker ?? ""}
            lot={editLotTarget?.lot ?? null}
          />
        </TabsContent>
        <TabsContent value="analytics">
          <AnalyticsPanel pid={id} />
        </TabsContent>
        <TabsContent value="strategies">
          <StrategyList pid={id} />
        </TabsContent>
        <TabsContent value="rebalance">
          <RebalancePanel pid={id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
