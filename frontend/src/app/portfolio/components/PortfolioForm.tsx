import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { usePortfolioStore } from "../store";

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated?: (id: string) => void;
}

export default function PortfolioForm({ open, onClose, onCreated }: Props) {
  const create = usePortfolioStore((s) => s.create);
  const [name, setName] = useState("");
  const [benchmark, setBenchmark] = useState("000300");
  const [cash, setCash] = useState("0");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    if (!name.trim()) return;
    setSubmitting(true);
    try {
      const id = await create({ name: name.trim(), benchmark, cash });
      setName(""); setBenchmark("000300"); setCash("0");
      onCreated?.(id);
      onClose();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新建组合</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>组合名称</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="如：主力" />
          </div>
          <div>
            <Label>基准</Label>
            <Input value={benchmark} onChange={(e) => setBenchmark(e.target.value)} />
          </div>
          <div>
            <Label>初始现金</Label>
            <Input value={cash} onChange={(e) => setCash(e.target.value)} type="number" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button onClick={handleSubmit} disabled={submitting || !name.trim()}>
            {submitting ? "创建中..." : "创建"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}