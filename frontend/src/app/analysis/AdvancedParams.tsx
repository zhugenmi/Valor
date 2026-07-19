type DatePreset = "1y" | "5y" | "1m" | "3m" | "6m";

export interface AdvancedParamsValue {
  startDate: string;
  endDate: string;
}

interface AdvancedParamsProps {
  value: AdvancedParamsValue;
  onChange: (v: AdvancedParamsValue) => void;
}

const PRESETS: { key: DatePreset; label: string; months: number }[] = [
  { key: "1m", label: "最近1月", months: 1 },
  { key: "3m", label: "最近3月", months: 3 },
  { key: "6m", label: "最近6月", months: 6 },
  { key: "1y", label: "最近1年", months: 12 },
  { key: "5y", label: "最近5年", months: 60 },
];

function fmtDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** Number of months between two ISO dates (approximate). */
function monthsBetween(start: string, end: string): number {
  const s = new Date(start);
  const e = new Date(end);
  return (
    (e.getFullYear() - s.getFullYear()) * 12 + (e.getMonth() - s.getMonth())
  );
}

export function defaultAnalysisDates(): { startDate: string; endDate: string } {
  const end = new Date();
  const start = new Date();
  start.setMonth(start.getMonth() - 12);
  return { startDate: fmtDate(start), endDate: fmtDate(end) };
}

export default function AdvancedParams({
  value,
  onChange,
}: AdvancedParamsProps) {
  const today = fmtDate(new Date());
  const activePreset: DatePreset | null =
    value.endDate === today
      ? (PRESETS.find(
          (p) => monthsBetween(value.startDate, value.endDate) === p.months,
        )?.key ?? null)
      : null;

  const handlePreset = (months: number) => {
    const end = new Date();
    const start = new Date();
    start.setMonth(start.getMonth() - months);
    onChange({ startDate: fmtDate(start), endDate: fmtDate(end) });
  };

  return (
    <div className="rounded-lg border bg-card p-3">
      <span className="mb-3 block font-medium">高级参数</span>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground text-sm">时间范围:</span>
        {PRESETS.map((p) => (
          <button
            key={p.key}
            type="button"
            onClick={() => handlePreset(p.months)}
            className={`rounded px-3 py-1 text-sm transition-colors ${
              activePreset === p.key
                ? "bg-primary text-primary-foreground"
                : "bg-muted hover:bg-muted/80"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-muted-foreground text-sm">开始日期</span>
          <input
            type="date"
            value={value.startDate}
            onChange={(e) => onChange({ ...value, startDate: e.target.value })}
            className="rounded border p-1"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-muted-foreground text-sm">结束日期</span>
          <input
            type="date"
            value={value.endDate}
            onChange={(e) => onChange({ ...value, endDate: e.target.value })}
            className="rounded border p-1"
          />
        </label>
      </div>
    </div>
  );
}
