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
import type { Lot } from "../types";

interface Props {
  pid: string;
  open: boolean;
  onClose: () => void;
  ticker: string;
  lot: Lot | null;
}

export default function EditLotForm({
  pid,
  open,
  onClose,
  ticker,
  lot,
}: Props) {
  const fetchDetail = usePortfolioStore((s) => s.fetchDetail);
  const [openDate, setOpenDate] = useState("");
  const [quantity, setQuantity] = useState("");
  const [costPrice, setCostPrice] = useState("");
  const [fees, setFees] = useState("0");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open && lot) {
      setOpenDate(lot.open_date);
      setQuantity(String(lot.quantity));
      setCostPrice(lot.cost_price);
      setFees(lot.fees);
      setNote(lot.note ?? "");
      setError(null);
    }
  }, [open, lot]);

  if (!lot) return null;

  async function submit() {
    if (!lot) return;
    const qty = Number(quantity);
    if (Number.isNaN(qty) || qty < 0) {
      setError("数量必须 >= 0");
      return;
    }
    try {
      await portfolioApi.updateLot(pid, ticker, lot.lot_id, {
        open_date: openDate,
        quantity: qty,
        cost_price: costPrice,
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
          <DialogTitle>编辑 Lot {lot.lot_id.slice(0, 8)}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>开仓日</Label>
            <Input
              value={openDate}
              onChange={(e) => setOpenDate(e.target.value)}
              type="date"
            />
          </div>
          <div>
            <Label>数量</Label>
            <Input
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              type="number"
            />
          </div>
          <div>
            <Label>成本价</Label>
            <Input
              value={costPrice}
              onChange={(e) => setCostPrice(e.target.value)}
              type="number"
            />
          </div>
          <div>
            <Label>手续费</Label>
            <Input
              value={fees}
              onChange={(e) => setFees(e.target.value)}
              type="number"
            />
          </div>
          <div>
            <Label>备注</Label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          {error && <div className="text-red-500 text-sm">{error}</div>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button onClick={submit}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
