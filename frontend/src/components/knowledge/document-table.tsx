import { useNavigate } from "react-router";
import { type KBDocListItem } from "@/api/knowledge";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const VINTAGE_VARIANT: Record<
  string,
  "default" | "secondary" | "destructive" | "outline"
> = {
  current: "default",
  recent: "secondary",
  legacy: "outline",
  obsolete: "destructive",
};

export function DocumentTable({
  documents,
  loading,
  onDelete,
}: {
  documents: KBDocListItem[];
  loading: boolean;
  onDelete?: (doc: KBDocListItem) => void;
}) {
  const navigate = useNavigate();
  const { t } = useTranslation();

  if (loading && documents.length === 0) {
    return (
      <div className="text-muted-foreground py-8 text-center">
        {t("knowledge.loading")}
      </div>
    );
  }
  if (!documents.length) {
    return (
      <div className="text-muted-foreground py-8 text-center">
        {t("knowledge.empty")}
      </div>
    );
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>标题</TableHead>
            <TableHead className="w-28">类别</TableHead>
            <TableHead className="w-32">发布日期</TableHead>
            <TableHead className="w-20">时效</TableHead>
            <TableHead className="w-20">chunks</TableHead>
            <TableHead className="w-20">状态</TableHead>
            <TableHead className="w-24"> </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {documents.map((doc) => (
            <TableRow
              key={doc.doc_id}
              className="cursor-pointer"
              onClick={() => navigate(`/knowledge/${doc.doc_id}`)}
            >
              <TableCell className="py-2">
                <div className="font-medium">{doc.title}</div>
                <div className="text-muted-foreground text-xs">
                  {doc.ticker ? `${doc.ticker} · ` : ""}
                  {doc.sub_type || doc.category}
                </div>
              </TableCell>
              <TableCell>
                <Badge variant="outline" className="text-xs">
                  {t(`knowledge.category.${doc.category}` as const)}
                </Badge>
              </TableCell>
              <TableCell className="text-xs">
                {doc.publish_date || "-"}
              </TableCell>
              <TableCell>
                {doc.vintage && (
                  <Badge
                    variant={VINTAGE_VARIANT[doc.vintage] ?? "outline"}
                    className="text-xs"
                  >
                    {t(`knowledge.vintage.${doc.vintage}` as const)}
                  </Badge>
                )}
              </TableCell>
              <TableCell className="text-xs">
                {doc.chunk_count ?? "-"}
              </TableCell>
              <TableCell className="text-xs">
                <span
                  className={
                    doc.status === "ready"
                      ? "text-green-600"
                      : doc.status === "failed"
                        ? "text-red-500"
                        : "text-muted-foreground"
                  }
                >
                  {doc.status}
                </span>
              </TableCell>
              <TableCell>
                {onDelete && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(doc);
                    }}
                  >
                    {t("knowledge.delete")}
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
