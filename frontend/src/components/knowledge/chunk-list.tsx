import { type KBChunk } from "@/api/knowledge";

export function ChunkList({
  chunks,
  onSelect,
}: {
  chunks: KBChunk[];
  onSelect?: (c: KBChunk) => void;
}) {
  if (!chunks.length) {
    return <div className="text-muted-foreground py-4 text-center">无分块</div>;
  }
  return (
    <div className="space-y-2">
      {chunks.map((c) => (
        <div
          key={c.chunk_id}
          className="cursor-pointer rounded border p-2 hover:bg-accent"
          onClick={() => onSelect?.(c)}
        >
          <div className="text-muted-foreground text-xs">
            #{c.seq} | page {c.page_no ?? "-"} | {c.heading_path ?? ""}
          </div>
          <div className="line-clamp-3 text-sm">{c.text}</div>
        </div>
      ))}
    </div>
  );
}
