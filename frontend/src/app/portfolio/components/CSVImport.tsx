import { useRef, useState } from "react";
import { Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { portfolioApi } from "@/api/portfolio";
import { usePortfolioStore } from "../store";

interface Props { pid: string; }

export default function CSVImport({ pid }: Props) {
  const ref = useRef<HTMLInputElement>(null);
  const fetchDetail = usePortfolioStore((s) => s.fetchDetail);
  const [uploading, setUploading] = useState(false);
  const [mode, setMode] = useState<"merge" | "replace">("merge");

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const result = await portfolioApi.importCsv(pid, file, mode);
      alert(`导入完成：${result.imported_rows}/${result.total_rows} 行（${result.format}）`);
      await fetchDetail(pid);
    } catch (err) {
      alert(`导入失败：${(err as Error).message}`);
    } finally {
      setUploading(false);
      if (ref.current) ref.current.value = "";
    }
  }

  return (
    <div className="flex items-center gap-2">
      <select className={cn("rounded border px-2 py-1 text-sm")} value={mode} onChange={(e) => setMode(e.target.value as "merge" | "replace")}>
        <option value="merge">追加</option>
        <option value="replace">替换</option>
      </select>
      <input ref={ref} type="file" accept=".csv" className="hidden" onChange={handleFile} />
      <Button variant="outline" size="sm" disabled={uploading} onClick={() => ref.current?.click()}>
        <Upload className={cn("mr-1 h-4 w-4")} /> {uploading ? "导入中..." : "导入 CSV"}
      </Button>
    </div>
  );
}