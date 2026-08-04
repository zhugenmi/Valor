import { ArrowLeft, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router";
import {
  kbApi,
  type KBCorrection,
  type KBDocListItem,
  type KBChunk,
} from "@/api/knowledge";
import { ChunkList } from "@/components/knowledge/chunk-list";
import { CorrectionsTable } from "@/components/knowledge/corrections-table";
import { PdfPreview } from "@/components/knowledge/pdf-preview";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useTranslation } from "react-i18next";

const VINTAGE_VARIANT: Record<
  string,
  "default" | "secondary" | "destructive" | "outline"
> = {
  current: "default",
  recent: "secondary",
  legacy: "outline",
  obsolete: "destructive",
};

export default function KnowledgeDetailPage() {
  const { docId } = useParams<{ docId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [doc, setDoc] = useState<KBDocListItem | null>(null);
  const [chunks, setChunks] = useState<KBChunk[]>([]);
  const [corrections, setCorrections] = useState<KBCorrection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reindexing, setReindexing] = useState(false);

  const loadAll = async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const [d, c, corr] = await Promise.all([
        kbApi.detail(id),
        kbApi.chunks(id),
        kbApi.corrections(id),
      ]);
      setDoc(d.data ?? null);
      setChunks(c.data ?? []);
      setCorrections(corr.data ?? []);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (docId) loadAll(docId);
  }, [docId]);

  const handleReindex = async () => {
    if (!docId) return;
    setReindexing(true);
    try {
      await kbApi.reindex(docId);
      await loadAll(docId);
    } finally {
      setReindexing(false);
    }
  };

  if (loading) {
    return <div className="text-muted-foreground p-6">{t("knowledge.loading")}</div>;
  }
  if (error || !doc) {
    return (
      <div className="p-6">
        <div className="text-red-500">{error ?? "文档不存在"}</div>
        <Button variant="outline" onClick={() => navigate("/knowledge")}>
          {t("knowledge.list")}
        </Button>
      </div>
    );
  }

  const isPdf = doc.mime_type === "application/pdf";
  const isDisclosure = doc.category === "disclosure";

  return (
    <div className="w-full px-6 py-6">
      <Button
        variant="ghost"
        size="sm"
        className="mb-3"
        onClick={() => navigate("/knowledge")}
      >
        <ArrowLeft className="mr-1 h-4 w-4" /> {t("knowledge.list")}
      </Button>

      <div className="mb-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="font-bold text-2xl">{doc.title}</h1>
            <div className="text-muted-foreground mt-1 text-sm">
              {t(`knowledge.category.${doc.category}` as const)} · {doc.sub_type}
              {doc.ticker ? ` · ${doc.ticker}` : ""}
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleReindex}
            disabled={reindexing}
          >
            <RefreshCw
              className={`mr-1 h-4 w-4 ${reindexing ? "animate-spin" : ""}`}
            />
            {t("knowledge.reindex")}
          </Button>
        </div>
        <div className="text-muted-foreground mt-2 flex flex-wrap gap-3 text-xs">
          <span>发布: {doc.publish_date || "-"}</span>
          <span>生效至: {doc.effective_until || "-"}</span>
          <span>上传: {doc.uploaded_at?.slice(0, 19).replace("T", ")")}</span>
          <span>策略: {doc.chunk_strategy || "-"}</span>
          <span>页数: {doc.page_count ?? "-"}</span>
          {doc.vintage && (
            <Badge variant={VINTAGE_VARIANT[doc.vintage] ?? "outline"}>
              {t(`knowledge.vintage.${doc.vintage}` as const)}
            </Badge>
          )}
          <Badge
            variant={doc.status === "ready" ? "default" : "secondary"}
            className="text-xs"
          >
            {doc.status}
          </Badge>
        </div>
        {doc.error_msg && (
          <div className="mt-2 rounded border border-red-300 bg-red-50 p-2 text-xs text-red-700">
            {doc.error_msg}
          </div>
        )}
      </div>

      <Tabs defaultValue="preview">
        <TabsList>
          <TabsTrigger value="preview">{t("knowledge.preview")}</TabsTrigger>
          <TabsTrigger value="chunks">
            {t("knowledge.chunks")} ({chunks.length})
          </TabsTrigger>
          {isDisclosure && (
            <TabsTrigger value="corrections">
              {t("knowledge.corrections")} ({corrections.length})
            </TabsTrigger>
          )}
        </TabsList>
        <TabsContent value="preview" className="mt-4">
          {isPdf ? (
            <PdfPreview docId={doc.doc_id} />
          ) : (
            <pre className="max-h-[70vh] overflow-auto rounded border p-3 text-xs whitespace-pre-wrap">
              {chunks.map((c) => c.text).join("\n\n")}
            </pre>
          )}
        </TabsContent>
        <TabsContent value="chunks" className="mt-4">
          <ChunkList chunks={chunks} />
        </TabsContent>
        {isDisclosure && (
          <TabsContent value="corrections" className="mt-4">
            <CorrectionsTable
              corrections={corrections}
              onRevoked={() =>
                docId &&
                kbApi.corrections(docId).then((r) => setCorrections(r.data ?? []))
              }
            />
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}
