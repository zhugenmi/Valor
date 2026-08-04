import { useEffect, useMemo, useState } from "react";
import { useDropzone } from "react-dropzone";
import { kbApi, type KBCategoryInfo } from "@/api/knowledge";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useTranslation } from "react-i18next";

export function UploadDialog({
  open,
  onOpenChange,
  onUploaded,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onUploaded: () => void;
}) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("research");
  const [subType, setSubType] = useState("公司研究");
  const [publishDate, setPublishDate] = useState("");
  const [enableCorrection, setEnableCorrection] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [categories, setCategories] = useState<KBCategoryInfo[]>([]);

  useEffect(() => {
    if (open && categories.length === 0) {
      kbApi.categories().then((res) => setCategories(res.data?.categories ?? []));
    }
  }, [open, categories.length]);

  const currentCat = useMemo(
    () => categories.find((c) => c.category === category),
    [categories, category],
  );

  useEffect(() => {
    if (currentCat && currentCat.sub_types.length > 0) {
      setSubType(currentCat.sub_types[0].name);
    }
  }, [currentCat]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (files) => {
      if (files[0]) {
        setFile(files[0]);
        if (!title) {
          setTitle(files[0].name.replace(/\.[^.]+$/, ""));
        }
      }
    },
  });

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("title", title || file.name.replace(/\.[^.]+$/, ""));
      fd.append("category", category);
      fd.append("sub_type", subType);
      if (publishDate) fd.append("publish_date", publishDate);
      fd.append("enable_correction", String(enableCorrection));
      await kbApi.upload(fd);
      onUploaded();
      onOpenChange(false);
      setFile(null);
      setTitle("");
      setPublishDate("");
    } finally {
      setUploading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("knowledge.upload")}</DialogTitle>
        </DialogHeader>
        <div
          {...getRootProps()}
          className={`cursor-pointer rounded border-2 border-dashed p-6 text-center transition-colors ${
            isDragActive ? "border-primary bg-accent" : "border-muted"
          }`}
        >
          <input {...getInputProps()} />
          {file ? (
            <div className="text-sm">
              <div className="font-medium">{file.name}</div>
              <div className="text-muted-foreground text-xs">
                {(file.size / 1024).toFixed(1)} KB · {file.type || "unknown"}
              </div>
            </div>
          ) : (
            <div className="text-muted-foreground text-sm">
              {t("knowledge.dropFile")}
            </div>
          )}
        </div>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label>标题</Label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="文档标题"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>类别</Label>
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {categories.map((c) => (
                    <SelectItem key={c.category} value={c.category}>
                      {t(`knowledge.category.${c.category}` as const)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>子类型</Label>
              <Select value={subType} onValueChange={setSubType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(currentCat?.sub_types ?? []).map((s) => (
                    <SelectItem key={s.name} value={s.name}>
                      {s.display_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>发布日期</Label>
              <Input
                type="date"
                value={publishDate}
                onChange={(e) => setPublishDate(e.target.value)}
              />
            </div>
            <div className="flex items-end gap-2">
              <input
                id="enable-correction"
                type="checkbox"
                checked={enableCorrection}
                onChange={(e) => setEnableCorrection(e.target.checked)}
                className="size-4"
              />
              <Label htmlFor="enable-correction" className="cursor-pointer">
                启用财报数据修正
              </Label>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleUpload} disabled={!file || uploading}>
            {uploading ? t("knowledge.uploading") : t("knowledge.upload")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
