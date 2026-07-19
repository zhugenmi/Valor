import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import AnalyticsPanel from "./components/AnalyticsPanel";
import CSVImport from "./components/CSVImport";
import HoldingForm from "./components/HoldingForm";
import HoldingsTable from "./components/HoldingsTable";
import RebalancePanel from "./components/RebalancePanel";
import StrategyList from "./components/StrategyList";
import { usePortfolioStore } from "./store";

export default function PortfolioDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { current, fetchDetail } = usePortfolioStore();
  const [showHoldingForm, setShowHoldingForm] = useState(false);

  useEffect(() => {
    if (id) fetchDetail(id);
  }, [id, fetchDetail]);

  if (!current || !id) return <div className="p-6">加载中...</div>;

  return (
    <div className={cn("mx-auto max-w-6xl p-6")}>
      <div className={cn("mb-6 flex items-center justify-between")}>
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
            <CSVImport pid={id} />
            <Button size="sm" onClick={() => setShowHoldingForm(true)}>
              <Plus className={cn("mr-1 h-4 w-4")} /> 新增持仓
            </Button>
          </div>
          <HoldingsTable pid={id} holdings={current.holdings} />
          <HoldingForm
            pid={id}
            open={showHoldingForm}
            onClose={() => setShowHoldingForm(false)}
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
