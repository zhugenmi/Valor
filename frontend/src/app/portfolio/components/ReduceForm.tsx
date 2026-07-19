import { useEffect, useState } from "react";
import { portfolioApi } from "@/api/portfolio";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { usePortfolioStore } from "../store";

interface Props {
  pid: string;
  open: boolean;
  onClose: () => void;
  ticker: string;
  name?: string | null;
  maxQuantity: number;
}

export default function ReduceForm({
  pid,
  open,
  onClose,
  ticker,
  name,
  maxQuantity,
}: Props) {
  const fetchDetail = usePortfolioStore((s) => s.fetchDetail);
  const [sellDate, setSellDate] = useState("");
  const [quantity, setQuantity] = useState("");
  const [sellPrice, setSellPrice] = useState("");
  const [fees, setFees] = useState("0");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setSellDate(new Date().toISOString().slice(0, 10));
      setQuantity("");
      setSellPrice("");
      setFees("0");
      setNote("");
      setError(null);
    }
  }, [open]);

  async function submit() {
    const qty = Number(quantity);
    if (!qty || qty <= 0) {
      setError("数量必须为正数");
      return;
    }
    if (qty > maxQuantity) {
      setError(`数量超过持仓量 ${maxQuantity}`);
      return;
    }
    if (!sellPrice) {
      setError("请填写卖出价");
      return;
    }
    try {
      await portfolioApi.addSell(pid, ticker, {
        sell_date: sellDate,
        quantity: qty,
        sell_price: sellPrice,
        fees: fees || "0",
        note: note.trim() || null,
      });
      await fetchDetail(pid);
      onClose();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>减仓 {ticker}{name ? ` · ${name}` : ""}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="text-gray-500 text-sm">
            当前持仓 {maxQuantity} 股
          </div>
          <div>
            <Label>卖出日期</Label>
            <Input
              value={sellDate}
              onChange={(e) => setSellDate(e.target.value)}
              type="date"
            />
          </div>
          <div>
            <Label>卖出数量</Label>
            <Input
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              type="number"
            />
          </div>
          <div>
            <Label>卖出价</Label>
            <Input
              value={sellPrice}
              onChange={(e) => setSellPrice(e.target.value)}
              type="number"
            />
          </div>
          <div>
            <Label>手续费（默认 0）</Label>
            <Input
              value={fees}
              onChange={(e) => setFees(e.target.value)}
              type="number"
            />
          </div>
          <div>
            <Label>备注（可选）</Label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          {error && <div className="text-red-500 text-sm">{error}</div>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button onClick={submit}>确认减仓</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
