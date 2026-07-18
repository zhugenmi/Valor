import { memo, useEffect, useMemo, useRef, useState } from "react";
import { loadTradingViewLib } from "./tv-load";

interface TradingViewTickerTapeProps {
  symbols: string[];
  theme?: "light" | "dark";
  locale?: string;
}

function TradingViewTickerTape({
  symbols,
  theme = "light",
  locale = "en",
}: TradingViewTickerTapeProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const widgetRef = useRef<InstanceType<Window["TradingView"]["TickerTape"]> | null>(null);
  const containerIdRef = useRef(
    `tv_tape_${Math.random().toString(36).slice(2, 10)}`,
  );
  const [failed, setFailed] = useState(false);

  const tapeSymbols = useMemo(
    () => symbols.slice(0, 8).map((s) => ({ proName: s })),
    [symbols],
  );

  useEffect(() => {
    setFailed(false);

    loadTradingViewLib()
      .then(() => {
        if (!containerRef.current) return;

        containerRef.current.innerHTML = "";
        const id = containerIdRef.current;
        containerRef.current.id = id;

        widgetRef.current = new window.TradingView.TickerTape({
          container_id: id,
          symbols: tapeSymbols,
          showSymbolLogo: true,
          colorTheme: theme,
          isTransparent: false,
          displayMode: "regular",
          locale,
        });
      })
      .catch(() => setFailed(true));

    return () => {
      widgetRef.current = null;
    };
  }, [tapeSymbols, theme, locale]);

  if (failed) {
    return (
      <div className="w-full rounded-md border border-dashed px-3 py-2 text-muted-foreground text-xs">
        行情条加载失败（TradingView CDN 不可达），请检查网络。
      </div>
    );
  }

  return (
    <div className="w-full">
      <div ref={containerRef} />
    </div>
  );
}

export default memo(TradingViewTickerTape);
