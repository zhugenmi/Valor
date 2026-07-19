import { useState } from "react";
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
}

export default function HoldingForm({ pid, open, onClose }: Props) {
  const fetchDetail = usePortfolioStore((s) => s.fetchDetail);
  const [ticker, setTicker] = useState("");
  const [name, setName] = useState("");
  const [quantity, setQuantity] = useState("");
  const [costPrice, setCostPrice] = useState("");
  const [openDate, setOpenDate] = useState("");

  async function submit() {
    if (!ticker.trim() || !quantity || !costPrice) return;
    await portfolioApi.addHolding(pid, {
      ticker: ticker.trim().padStart(6, "0"),
      name: name.trim() || undefined,
      side: "long",
      lots: [
        {
          lot_id: "",
          open_date: openDate || new Date().toISOString().slice(0, 10),
          quantity: Number(quantity),
          cost_price: costPrice,
          fees: "0",
        },
      ],
    });
    setTicker("");
    setName("");
    setQuantity("");
    setCostPrice("");
    setOpenDate("");
    await fetchDetail(pid);
    onClose();
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新增持仓</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>股票代码</Label>
            <Input
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="600519"
            />
          </div>
          <div>
            <Label>名称（可选）</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
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
            <Label>开仓日</Label>
            <Input
              value={openDate}
              onChange={(e) => setOpenDate(e.target.value)}
              type="date"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button
            onClick={submit}
            disabled={!ticker || !quantity || !costPrice}
          >
            添加
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
