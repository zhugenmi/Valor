import { useState } from "react";
import { Link } from "react-router";
import { ChevronDown, ChevronRight, Stethoscope, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { portfolioApi } from "@/api/portfolio";
import { usePortfolioStore } from "../store";
import type { Holding } from "../types";

interface Props {
  pid: string;
  holdings: Holding[];
}

export default function HoldingsTable({ pid, holdings }: Props) {
  const fetchDetail = usePortfolioStore((s) => s.fetchDetail);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggle(ticker: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  }

  async function removeHolding(ticker: string) {
    if (!confirm(`删除持仓 ${ticker}？`)) return;
    await portfolioApi.deleteHolding(pid, ticker);
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
          <TableHead className="text-right">Lot 数</TableHead>
          <TableHead className="text-right">操作</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {holdings.map((h) => (
          <>
            <TableRow key={h.ticker}>
              <TableCell onClick={() => toggle(h.ticker)} className="cursor-pointer">
                {expanded.has(h.ticker) ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              </TableCell>
              <TableCell className="font-mono">{h.ticker}</TableCell>
              <TableCell>{h.name || "-"}</TableCell>
              <TableCell className="text-right">{h.lots.reduce((s, l) => s + l.quantity, 0)}</TableCell>
              <TableCell className="text-right">{h.lots.length}</TableCell>
              <TableCell className="space-x-1 text-right">
                <Button variant="ghost" size="icon" asChild>
                  <Link to={`/analysis?ticker=${h.ticker}`}><Stethoscope className="h-4 w-4" /></Link>
                </Button>
                <Button variant="ghost" size="icon" onClick={() => removeHolding(h.ticker)}>
                  <Trash2 className="h-4 w-4 text-red-500" />
                </Button>
              </TableCell>
            </TableRow>
            {expanded.has(h.ticker) && h.lots.map((lot) => (
              <TableRow key={lot.lot_id} className="bg-gray-50">
                <TableCell></TableCell>
                <TableCell colSpan={5} className="text-gray-600 text-sm">
                  Lot {lot.lot_id.slice(0, 8)}：{lot.open_date} · {lot.quantity} 股 @ ¥{lot.cost_price}
                  {Number(lot.fees) > 0 && ` · 手续费 ¥${lot.fees}`}
                </TableCell>
              </TableRow>
            ))}
          </>
        ))}
        {holdings.length === 0 && (
          <TableRow>
            <TableCell colSpan={6} className="py-8 text-center text-gray-500">暂无持仓，点击「导入 CSV」或「新增持仓」</TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
}