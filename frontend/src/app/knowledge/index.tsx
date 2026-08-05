import { Plus, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { kbApi, type KBCategoryInfo } from "@/api/knowledge";
import { DocumentTable } from "@/components/knowledge/document-table";
import { UploadDialog } from "@/components/knowledge/upload-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useKnowledgeStore } from "@/store/knowledge";

const CATEGORY_ALL = "all";

export default function KnowledgeListPage() {
  const { t } = useTranslation();
  const { documents, total, loading, error, fetchDocuments } = useKnowledgeStore();
  const [categories, setCategories] = useState<KBCategoryInfo[]>([]);
  const [category, setCategory] = useState<string>(CATEGORY_ALL);
  const [ticker, setTicker] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);

  useEffect(() => {
    kbApi.categories().then((res) => setCategories(res.data?.categories ?? []));
  }, []);

  useEffect(() => {
    fetchDocuments({
      category: category === CATEGORY_ALL ? undefined : category,
      ticker: ticker || undefined,
      limit: 50,
    });
  }, [category, ticker, fetchDocuments]);

  const handleDelete = async (doc: { doc_id: string; title: string }) => {
    if (!confirm(`${t("knowledge.deleteConfirm")}\n${doc.title}`)) return;
    await kbApi.delete(doc.doc_id);
    fetchDocuments({
      category: category === CATEGORY_ALL ? undefined : category,
      ticker: ticker || undefined,
      limit: 50,
    });
  };

  return (
    <div className="w-full px-6 py-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-bold text-2xl">{t("knowledge.title")}</h1>
          <div className="text-muted-foreground text-sm">
            共 {total} 篇文档
          </div>
        </div>
        <Button onClick={() => setUploadOpen(true)}>
          <Plus className="mr-1 h-4 w-4" /> {t("knowledge.upload")}
        </Button>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        <Select value={category} onValueChange={setCategory}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="全部类别" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={CATEGORY_ALL}>全部</SelectItem>
            {categories.map((c) => (
              <SelectItem key={c.category} value={c.category}>
                {t(`knowledge.category.${c.category}` as const)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute top-1/2 left-2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            placeholder="搜索文档"
            className="pl-8"
          />
        </div>
      </div>

      {error && <div className="mb-4 text-red-500">{error}</div>}

      <DocumentTable
        documents={documents}
        loading={loading}
        onDelete={handleDelete}
      />

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onUploaded={() =>
          fetchDocuments({
            category: category === CATEGORY_ALL ? undefined : category,
            ticker: ticker || undefined,
            limit: 50,
          })
        }
      />
    </div>
  );
}
