import { ArrowLeft, Plus, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { portfolioApi } from "@/api/portfolio";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";
import AnalyticsPanel from "./components/AnalyticsPanel";
import CSVImport from "./components/CSVImport";
import EditLotForm from "./components/EditLotForm";
import HoldingForm from "./components/HoldingForm";
import HoldingsTable from "./components/HoldingsTable";
import RebalancePanel from "./components/RebalancePanel";
import ReduceForm from "./components/ReduceForm";
import StrategyList from "./components/StrategyList";
import { usePortfolioStore } from "./store";
import type { Lot } from "./types";

export default function PortfolioDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { current, analytics, fetchDetail, fetchAnalytics, analyticsLoading } =
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
  const [editingCash, setEditingCash] = useState(false);
  const [cashInput, setCashInput] = useState("");
  const cashInputRef = useRef<HTMLInputElement>(null);
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const nameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editingCash && cashInputRef.current) {
      cashInputRef.current.focus();
      cashInputRef.current.select();
    }
  }, [editingCash]);

  useEffect(() => {
    if (editingName && nameInputRef.current) {
      nameInputRef.current.focus();
      nameInputRef.current.select();
    }
  }, [editingName]);

  useEffect(() => {
    if (id) fetchDetail(id);
  }, [id, fetchDetail]);

  const saveCash = useCallback(async () => {
    if (!id) return;
    const val = cashInput.trim();
    if (!val || Number(val) < 0) return;
    await portfolioApi.update(id, { cash: val } as Record<string, unknown>);
    setEditingCash(false);
    await fetchDetail(id);
  }, [id, cashInput, fetchDetail]);

  const saveName = useCallback(async () => {
    if (!id) return;
    const val = nameInput.trim();
    if (!val) return;
    await portfolioApi.update(id, { name: val } as Record<string, unknown>);
    setEditingName(false);
    await fetchDetail(id);
  }, [id, nameInput, fetchDetail]);

  if (!current || !id) return <div className="p-6">加载中...</div>;

  function qtyOf(ticker: string): number {
    const h = current?.holdings.find((x) => x.ticker === ticker);
    if (!h) return 0;
    return h.lots.reduce((s, l) => s + l.quantity, 0);
  }

  return (
    <div className={cn("mx-auto w-full max-w-6xl p-6 [scrollbar-gutter:stable]")}>
      <div className="mb-6">
        <div className="mb-2 flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate("/portfolio")}
            title="返回组合列表"
          >
            <ArrowLeft className="h-5 w-5" />
          </Button>
          {editingName ? (
            <Input
              ref={nameInputRef}
              className="inline h-8 w-64 px-1 py-0 font-bold text-2xl"
              value={nameInput}
              onChange={(e) => setNameInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") saveName();
                if (e.key === "Escape") setEditingName(false);
              }}
              onBlur={saveName}
            />
          ) : (
            <h1
              className="cursor-pointer border-transparent border-b border-dotted font-bold text-2xl hover:border-muted-foreground/40"
              onClick={() => {
                setNameInput(current.name);
                setEditingName(true);
              }}
            >
              {current.name}
            </h1>
          )}
        </div>
        <div className="ml-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-muted-foreground text-sm">
          <span className="flex items-center gap-1">
            市值
            {analytics?.total_market_value ? (
              <span className="font-medium text-foreground">
                {formatMoney(analytics.total_market_value)}
              </span>
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </span>
          <span className="text-muted-foreground/40">|</span>
          <span>基准 {current.benchmark}</span>
          <span className="text-muted-foreground/40">|</span>
          <span>持仓 {current.holdings.length} 只</span>
          <span className="text-muted-foreground/40">|</span>
          <span className="flex items-center gap-1">
            现金
            {editingCash ? (
              <Input
                ref={cashInputRef}
                className="inline h-6 w-28 px-1 py-0 text-xs"
                value={cashInput}
                onChange={(e) => setCashInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") saveCash();
                  if (e.key === "Escape") setEditingCash(false);
                }}
                onBlur={saveCash}
                type="number"
                step="0.01"
              />
            ) : (
              <button
                type="button"
                className="cursor-pointer border-muted-foreground/40 border-b border-dotted hover:border-muted-foreground"
                onClick={() => {
                  setCashInput(current.cash);
                  setEditingCash(true);
                }}
              >
                ¥{Number(current.cash).toLocaleString()}
              </button>
            )}
          </span>
        </div>
      </div>
      <Tabs defaultValue="holdings">
        <div className="mb-4 flex items-center justify-between">
          <TabsList>
            <TabsTrigger value="holdings">持仓</TabsTrigger>
            <TabsTrigger value="analytics">分析</TabsTrigger>
            <TabsTrigger value="strategies">策略</TabsTrigger>
            <TabsTrigger value="rebalance">调仓</TabsTrigger>
          </TabsList>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => id && fetchAnalytics(id)}
              disabled={analyticsLoading}
            >
              <RefreshCw
                className={cn(
                  "mr-1 h-4 w-4",
                  analyticsLoading && "animate-spin",
                )}
              />
              {analyticsLoading ? "刷新中..." : "刷新行情"}
            </Button>
            <CSVImport pid={id} />
            <Button size="sm" onClick={() => setShowCreateForm(true)}>
              <Plus className={cn("mr-1 h-4 w-4")} /> 新增持仓
            </Button>
          </div>
        </div>
        <TabsContent
          value="holdings"
          className="min-h-[300px] w-full space-y-4"
        >
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
        <TabsContent
          value="analytics"
          className="min-h-[300px] w-full space-y-4"
        >
          <AnalyticsPanel pid={id} />
        </TabsContent>
        <TabsContent
          value="strategies"
          className="min-h-[300px] w-full space-y-4"
        >
          <StrategyList pid={id} />
        </TabsContent>
        <TabsContent
          value="rebalance"
          className="min-h-[300px] w-full space-y-4"
        >
          <RebalancePanel pid={id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
