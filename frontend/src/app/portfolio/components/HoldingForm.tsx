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
  mode: "create" | "append";
  ticker?: string;
  name?: string | null;
}

export default function HoldingForm({
  pid,
  open,
  onClose,
  mode,
  ticker,
  name,
}: Props) {
  const fetchDetail = usePortfolioStore((s) => s.fetchDetail);
  const [submitting, setSubmitting] = useState(false);
  const [tickerInput, setTickerInput] = useState("");
  const [nameInput, setNameInput] = useState("");
  const [quantity, setQuantity] = useState("");
  const [costPrice, setCostPrice] = useState("");
  const [openDate, setOpenDate] = useState("");
  const [fees, setFees] = useState("0");
  const [note, setNote] = useState("");

  useEffect(() => {
    if (open) {
      setTickerInput(mode === "append" ? (ticker ?? "") : "");
      setNameInput(mode === "append" ? (name ?? "") : "");
      setQuantity("");
      setCostPrice("");
      setOpenDate(new Date().toISOString().slice(0, 10));
      setFees("0");
      setNote("");
    }
  }, [open, mode, ticker, name]);

  const isCreate = mode === "create";

  async function submit() {
    if (submitting) return;
    setSubmitting(true);
    try {
      const t = (
        isCreate ? tickerInput.trim().padStart(6, "0") : (ticker ?? "")
      ).trim();
      if (!t || !quantity || !costPrice) return;
      const lotPayload = {
        lot_id: "",
        open_date: openDate || new Date().toISOString().slice(0, 10),
        quantity: Number(quantity),
        cost_price: costPrice,
        fees: fees || "0",
        note: note.trim() || null,
      };
      if (isCreate) {
        await portfolioApi.addHolding(pid, {
          ticker: t,
          name: nameInput.trim() || undefined,
          side: "long",
          lots: [lotPayload],
        });
      } else {
        await portfolioApi.addLot(pid, t, lotPayload);
      }
      await fetchDetail(pid);
      onClose();
    } finally {
      setSubmitting(false);
    }
  }

  const valid =
    (isCreate ? !!tickerInput.trim() : !!ticker) && !!quantity && !!costPrice;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isCreate ? "新增持仓" : `增持 ${ticker}`}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          {isCreate && (
            <>
              <div>
                <Label>股票代码</Label>
                <Input
                  value={tickerInput}
                  onChange={(e) => setTickerInput(e.target.value)}
                  placeholder="600519"
                />
              </div>
              <div>
                <Label>名称（可选）</Label>
                <Input
                  value={nameInput}
                  onChange={(e) => setNameInput(e.target.value)}
                />
              </div>
            </>
          )}
          <div>
            <Label>买入日期</Label>
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
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button onClick={submit} disabled={!valid || submitting}>
            {submitting ? "提交中…" : isCreate ? "添加" : "增持"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
