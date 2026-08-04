import { kbApi, type KBCorrection } from "@/api/knowledge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useTranslation } from "react-i18next";

function fmtDiff(c: KBCorrection): string {
  if (!c.original_value) return "-";
  const orig = parseFloat(c.original_value);
  const corr = parseFloat(c.corrected_value);
  if (Number.isNaN(orig) || Number.isNaN(corr) || orig === 0) return "-";
  return `${(Math.abs(corr - orig) / Math.abs(orig) * 100).toFixed(2)}%`;
}

export function CorrectionsTable({
  corrections,
  onRevoked,
}: {
  corrections: KBCorrection[];
  onRevoked: () => void;
}) {
  const { t } = useTranslation();
  if (!corrections.length) {
    return (
      <div className="text-muted-foreground py-4 text-center">
        {t("knowledge.noCorrections")}
      </div>
    );
  }
  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>字段</TableHead>
            <TableHead>原值</TableHead>
            <TableHead>修正值</TableHead>
            <TableHead>差异</TableHead>
            <TableHead>来源页</TableHead>
            <TableHead>修正时间</TableHead>
            <TableHead> </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {corrections.map((c) => (
            <TableRow key={c.correction_id}>
              <TableCell className="font-medium">{c.field_name}</TableCell>
              <TableCell className="text-xs">{c.original_value ?? "-"}</TableCell>
              <TableCell className="text-green-600">
                {c.corrected_value}
                {c.unit ? ` ${c.unit}` : ""}
              </TableCell>
              <TableCell className="text-xs">{fmtDiff(c)}</TableCell>
              <TableCell className="text-xs">{c.source_page ?? "-"}</TableCell>
              <TableCell className="text-xs">
                {c.corrected_at?.slice(0, 19).replace("T", " ") ?? "-"}
              </TableCell>
              <TableCell>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={async () => {
                    await kbApi.revokeCorrection(c.correction_id);
                    onRevoked();
                  }}
                >
                  {t("knowledge.revoke")}
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
