import {
  ChevronDown,
  ChevronRight,
  Minus,
  Pencil,
  Plus,
  Stethoscope,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { portfolioApi } from "@/api/portfolio";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatMoney, formatPercent, formatPnlClass } from "@/lib/format";
import { usePortfolioStore } from "../store";
import type { Holding, Lot, SellLot } from "../types";

interface Props {
  pid: string;
  holdings: Holding[];
  onAppend: (ticker: string, name: string | null) => void;
  onReduce: (ticker: string, name: string | null) => void;
  onEditLot: (ticker: string, lot: Lot) => void;
}

export default function HoldingsTable({
  pid,
  holdings,
  onAppend,
  onReduce,
  onEditLot,
}: Props) {
  const { analytics, fetchDetail } = usePortfolioStore();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggle(ticker: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  }

  function metricFor(ticker: string) {
    return analytics?.positions.find((p) => p.ticker === ticker);
  }

  async function removeHolding(ticker: string) {
    if (!confirm(`删除持仓 ${ticker}？此操作会移除所有 Lot 与 SellLot 记录。`))
      return;
    await portfolioApi.deleteHolding(pid, ticker);
    await fetchDetail(pid);
  }

  async function removeLot(ticker: string, lotId: string) {
    if (!confirm(`删除 Lot ${lotId.slice(0, 8)}？`)) return;
    await portfolioApi.deleteLot(pid, ticker, lotId);
    await fetchDetail(pid);
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-8"></TableHead>
          <TableHead>代码</TableHead>
          <TableHead>名称</TableHead>
          <TableHead className="text-right">持仓量</TableHead>
          <TableHead className="text-right">买入均价</TableHead>
          <TableHead className="text-right">现价</TableHead>
          <TableHead className="text-right">浮动盈亏</TableHead>
          <TableHead className="text-right">个股仓位</TableHead>
          <TableHead className="text-right">操作</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {holdings.map((h) => {
          const m = metricFor(h.ticker);
          const qty = h.lots.reduce((s, l) => s + l.quantity, 0);
          const expandedRow = expanded.has(h.ticker);
          return (
            <>
              <TableRow key={h.ticker}>
                <TableCell
                  onClick={() => toggle(h.ticker)}
                  className="cursor-pointer"
                >
                  {expandedRow ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                </TableCell>
                <TableCell className="font-mono">{h.ticker}</TableCell>
                <TableCell>{h.name || "-"}</TableCell>
                <TableCell className="text-right">{qty}</TableCell>
                <TableCell className="text-right">
                  {m ? formatMoney(m.cost_price) : "-"}
                </TableCell>
                <TableCell className="text-right">
                  {m ? formatMoney(m.current_price) : "-"}
                </TableCell>
                <TableCell
                  className={`text-right ${m ? formatPnlClass(m.unrealized_pnl) : ""}`}
                >
                  {m
                    ? `${formatMoney(m.unrealized_pnl)} (${formatPercent(m.unrealized_pnl_pct)})`
                    : "-"}
                </TableCell>
                <TableCell className="text-right">
                  {m ? formatPercent(m.weight) : "-"}
                </TableCell>
                <TableCell className="space-x-1 text-right">
                  <Button variant="ghost" size="icon" asChild title="诊断">
                    <Link to={`/analysis?ticker=${h.ticker}`}>
                      <Stethoscope className="h-4 w-4" />
                    </Link>
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    title="增持"
                    onClick={() => onAppend(h.ticker, h.name ?? null)}
                  >
                    <Plus className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    title="减仓"
                    onClick={() => onReduce(h.ticker, h.name ?? null)}
                    disabled={qty === 0}
                  >
                    <Minus className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    title="删除持仓"
                    onClick={() => removeHolding(h.ticker)}
                  >
                    <Trash2 className="h-4 w-4 text-red-500" />
                  </Button>
                </TableCell>
              </TableRow>
              {expandedRow && (
                <>
                  {h.lots.map((lot) => (
                    <TableRow key={lot.lot_id} className="bg-gray-50">
                      <TableCell></TableCell>
                      <TableCell colSpan={8} className="text-gray-700 text-sm">
                        <div className="flex items-center justify-between">
                          <span>
                            Lot {lot.lot_id.slice(0, 8)}：{lot.open_date} ·{" "}
                            {lot.quantity} 股 @ ¥{lot.cost_price}
                            {Number(lot.fees) > 0 && ` · 手续费 ¥${lot.fees}`}
                            {lot.note && ` · ${lot.note}`}
                          </span>
                          <span className="space-x-1">
                            <Button
                              variant="ghost"
                              size="icon"
                              title="编辑 Lot"
                              onClick={() => onEditLot(h.ticker, lot)}
                            >
                              <Pencil className="h-3 w-3" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              title="删除 Lot"
                              onClick={() => removeLot(h.ticker, lot.lot_id)}
                            >
                              <Trash2 className="h-3 w-3 text-red-500" />
                            </Button>
                          </span>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                  {(h.sell_lots ?? []).map((s: SellLot) => (
                    <TableRow key={s.sell_id} className="bg-amber-50">
                      <TableCell></TableCell>
                      <TableCell colSpan={8} className="text-gray-700 text-sm">
                        卖出 {s.sell_id.slice(0, 8)}：{s.sell_date} ·{" "}
                        {s.quantity} 股 @ ¥{s.sell_price}
                        {Number(s.fees) > 0 && ` · 手续费 ¥${s.fees}`} ·
                        已实现盈亏{" "}
                        <span className={formatPnlClass(s.realized_pnl)}>
                          ¥{s.realized_pnl}
                        </span>
                        {s.note && ` · ${s.note}`}
                      </TableCell>
                    </TableRow>
                  ))}
                  {h.lots.length === 0 && (h.sell_lots ?? []).length === 0 && (
                    <TableRow className="bg-gray-50">
                      <TableCell></TableCell>
                      <TableCell colSpan={8} className="text-gray-400 text-sm">
                        已清仓（无 Lot 与 SellLot 记录）
                      </TableCell>
                    </TableRow>
                  )}
                </>
              )}
            </>
          );
        })}
        {holdings.length === 0 && (
          <TableRow>
            <TableCell colSpan={9} className="py-8 text-center text-gray-500">
              暂无持仓，点击「导入 CSV」或「新增持仓」
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
}
