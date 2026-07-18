/**
 * Shared TradingView library loader.
 * Loads tv.js once and caches the promise.
 */
declare global {
  interface Window {
    TradingView: {
      widget: new (options: Record<string, unknown>) => unknown;
      TickerTape: new (options: Record<string, unknown>) => unknown;
    };
  }
}

let loadPromise: Promise<void> | null = null;

export function loadTradingViewLib(): Promise<void> {
  if (loadPromise) return loadPromise;

  if (typeof window.TradingView !== "undefined") {
    loadPromise = Promise.resolve();
    return loadPromise;
  }

  loadPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/tv.js";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => {
      loadPromise = null;
      reject(new Error("Failed to load TradingView library"));
    };
    document.head.appendChild(script);
  });

  return loadPromise;
}
