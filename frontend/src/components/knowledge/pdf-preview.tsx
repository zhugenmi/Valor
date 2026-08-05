import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

export function PdfPreview({ docId }: { docId: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [searchParams] = useSearchParams();
  const targetPage = searchParams.get("page");
  const targetChunk = searchParams.get("chunk");
  const [pageNum, setPageNum] = useState(() => parseInt(targetPage || "1", 10));
  const [totalPages, setTotalPages] = useState(0);
  const [pdfDoc, setPdfDoc] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    import("pdfjs-dist")
      .then((pdfjsLib: any) => {
        if (cancelled) return;
        pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;
        const loadingTask = pdfjsLib.getDocument({
          url: `/api/v1/kb/documents/${docId}/file`,
          withCredentials: true,
        });
        loadingTask.promise.then(
          (pdf: any) => {
            if (cancelled) return;
            setPdfDoc(pdf);
            setTotalPages(pdf.numPages);
            setLoading(false);
          },
          (err: Error) => {
            if (cancelled) return;
            setError(err?.message ?? "PDF load failed");
            setLoading(false);
          },
        );
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err?.message ?? "pdfjs-dist import failed");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [docId]);

  const renderPage = (pdf: any, num: number) => {
    pdf.getPage(num).then((page: any) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const viewport = page.getViewport({ scale: 1.2 });
      canvas.height = viewport.height;
      canvas.width = viewport.width;
      page.render({ canvasContext: ctx, viewport });
    });
  };

  useEffect(() => {
    if (pdfDoc) renderPage(pdfDoc, pageNum);
  }, [pageNum, pdfDoc]);

  if (loading) return <div className="text-muted-foreground py-8 text-center">PDF 加载中...</div>;
  if (error)
    return <div className="text-red-500 py-8 text-center">PDF 加载失败: {error}</div>;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={pageNum <= 1}
          onClick={() => setPageNum((p) => p - 1)}
          className="rounded border px-3 py-1 text-sm disabled:opacity-50"
        >
          上一页
        </button>
        <span className="text-sm">
          {pageNum} / {totalPages}
        </span>
        <button
          type="button"
          disabled={pageNum >= totalPages}
          onClick={() => setPageNum((p) => p + 1)}
          className="rounded border px-3 py-1 text-sm disabled:opacity-50"
        >
          下一页
        </button>
        {targetChunk && (
          <span className="text-yellow-600 text-xs">
            高亮 chunk: {targetChunk}
          </span>
        )}
      </div>
      <canvas ref={canvasRef} className="border" />
    </div>
  );
}
