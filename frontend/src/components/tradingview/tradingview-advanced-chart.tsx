import { memo, useEffect, useMemo, useRef, useState } from "react";
import defaultMap from "./tv-symbol-map.json";
import { loadTradingViewLib } from "./tv-load";

interface TradingViewAdvancedChartProps {
  ticker: string;
  mappingUrl?: string;
  interval?: string;
  minHeight?: number;
  theme?: "light" | "dark";
  locale?: string;
  timezone?: string;
}

function TradingViewAdvancedChart({
  ticker,
  mappingUrl,
  interval = "D",
  minHeight = 420,
  theme = "light",
  locale = "en",
  timezone = "UTC",
}: TradingViewAdvancedChartProps) {
  const symbolMapRef = useRef<Record<string, string>>(
    defaultMap as Record<string, string>,
  );
  const containerRef = useRef<HTMLDivElement | null>(null);
  const widgetRef = useRef<InstanceType<Window["TradingView"]["widget"]> | null>(null);
  const containerIdRef = useRef(
    `tv_chart_${Math.random().toString(36).slice(2, 10)}`,
  );
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!mappingUrl) return;
    let cancelled = false;
    fetch(mappingUrl)
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then((json) => {
        if (!cancelled)
          symbolMapRef.current = (json || {}) as Record<string, string>;
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [mappingUrl]);

  const tvSymbol = useMemo(() => {
    const t = ticker;
    if (typeof t === "string" && t.includes(":")) {
      const [ex, sym] = t.split(":");
      const exUpper = ex.toUpperCase();
      if (exUpper === "HKEX") {
        const norm = (sym ?? "").replace(/^0+/, "") || "0";
        return `${exUpper}:${norm}`;
      }
    }
    const m = symbolMapRef.current;
    if (m && typeof m === "object" && t in m) {
      const v = m[t];
      if (typeof v === "string" && v.length > 0) return v;
    }
    return t;
  }, [ticker]);

  useEffect(() => {
    setFailed(false);

    loadTradingViewLib()
      .then(() => {
        if (!containerRef.current) return;

        containerRef.current.innerHTML = "";
        const id = containerIdRef.current;
        containerRef.current.id = id;

        widgetRef.current = new window.TradingView.widget({
          container_id: id,
          symbol: tvSymbol,
          interval,
          timezone,
          theme,
          style: "1",
          locale,
          autosize: true,
          allow_symbol_change: true,
          enable_publishing: false,
          hideideas: true,
          toolbar_bg: theme === "light" ? "#f1f3f6" : "#2a2e39",
          disabled_features: [
            "left_toolbar",
            "header_symbol_detail",
            "calendar",
            "symbol_search_hot_keywords",
          ],
          studies: [],
        });
      })
      .catch(() => setFailed(true));

    return () => {
      widgetRef.current = null;
    };
  }, [tvSymbol, interval, theme, locale, timezone]);

  if (failed) {
    return (
      <section
        aria-label="Trading chart"
        className="flex w-full items-center justify-center rounded-md border border-dashed text-muted-foreground text-sm"
        style={{ height: minHeight }}
      >
        图表加载失败（TradingView CDN 不可达），请检查网络。
      </section>
    );
  }

  return (
    <section
      aria-label="Trading chart"
      className="w-full"
      style={{ height: minHeight }}
    >
      <div ref={containerRef} className="h-full" />
      <div className="tradingview-widget-copyright">
        <a
          href={`https://www.tradingview.com/symbols/${String(tvSymbol).replace(":", "-")}/`}
          rel="noopener noreferrer nofollow"
          target="_blank"
          aria-label="Open symbol on TradingView"
        >
          <span className="blue-text">
            {String(tvSymbol).replace(":", "/")} chart
          </span>
        </a>
        <span className="trademark"> by TradingView</span>
      </div>
    </section>
  );
}

export default memo(TradingViewAdvancedChart);
