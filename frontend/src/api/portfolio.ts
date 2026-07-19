import type {
  Holding,
  ImportResult,
  Lot,
  Portfolio,
  PortfolioAnalytics,
  PortfolioSummary,
  RebalancePlan,
  SellLot,
  Strategy,
} from "@/app/portfolio/types";
import { apiClient } from "@/lib/api-client";

export interface CreatePortfolioInput {
  name: string;
  benchmark?: string;
  cash?: string;
}

export interface UpdatePortfolioInput {
  name?: string;
  benchmark?: string;
  cash?: string;
}

export interface StrategyRequest {
  method: "equal_weight" | "mean_variance" | "risk_parity";
  tickers: string[];
  params?: Record<string, unknown>;
}

const BASE = "/portfolios";

export const portfolioApi = {
  list: () => apiClient.get<PortfolioSummary[]>(BASE),
  create: (input: CreatePortfolioInput) =>
    apiClient.post<Portfolio>(BASE, input),
  get: (pid: string) => apiClient.get<Portfolio>(`${BASE}/${pid}`),
  update: (pid: string, input: UpdatePortfolioInput) =>
    apiClient.put<Portfolio>(`${BASE}/${pid}`, input),
  delete: (pid: string) =>
    apiClient.delete<{ deleted: string }>(`${BASE}/${pid}`),
  importCsv: (pid: string, file: File, mode: "merge" | "replace" = "merge") => {
    const form = new FormData();
    form.append("file", file);
    return apiClient.post<ImportResult>(
      `${BASE}/${pid}/import?mode=${mode}`,
      form,
    );
  },
  listHoldings: (pid: string) =>
    apiClient.get<Holding[]>(`${BASE}/${pid}/holdings`),
  addHolding: (pid: string, h: Omit<Holding, "lots"> & { lots: Lot[] }) =>
    apiClient.post<Holding>(`${BASE}/${pid}/holdings`, h),
  updateHolding: (pid: string, ticker: string, h: Holding) =>
    apiClient.put<Portfolio>(`${BASE}/${pid}/holdings/${ticker}`, h),
  deleteHolding: (pid: string, ticker: string) =>
    apiClient.delete<{ deleted: string }>(`${BASE}/${pid}/holdings/${ticker}`),
  addLot: (pid: string, ticker: string, lot: Omit<Lot, "lot_id">) =>
    apiClient.post<Holding>(`${BASE}/${pid}/holdings/${ticker}/lots`, lot),
  addSell: (
    pid: string,
    ticker: string,
    sell: Omit<SellLot, "sell_id" | "realized_pnl" | "avg_cost_at_sell">,
  ) => apiClient.post<SellLot>(`${BASE}/${pid}/holdings/${ticker}/sells`, sell),
  updateLot: (
    pid: string,
    ticker: string,
    lotId: string,
    patch: Partial<Omit<Lot, "lot_id">>,
  ) =>
    apiClient.put<Portfolio>(
      `${BASE}/${pid}/holdings/${ticker}/lots/${lotId}`,
      patch,
    ),
  deleteLot: (pid: string, ticker: string, lotId: string) =>
    apiClient.delete<{ deleted: string }>(
      `${BASE}/${pid}/holdings/${ticker}/lots/${lotId}`,
    ),
  analytics: (pid: string) =>
    apiClient.get<PortfolioAnalytics>(`${BASE}/${pid}/analytics`),
  createStrategy: (pid: string, req: StrategyRequest) =>
    apiClient.post<
      Strategy & {
        sharpe?: number | null;
        diagnostics?: Record<string, unknown>;
      }
    >(`${BASE}/${pid}/strategies`, req),
  listStrategies: (pid: string) =>
    apiClient.get<Strategy[]>(`${BASE}/${pid}/strategies`),
  deleteStrategy: (pid: string, sid: string) =>
    apiClient.delete<{ deleted: string }>(`${BASE}/${pid}/strategies/${sid}`),
  rebalance: (
    pid: string,
    strategyId: string,
    params: Record<string, unknown> = {},
  ) =>
    apiClient.post<RebalancePlan>(`${BASE}/${pid}/rebalance`, {
      strategy_id: strategyId,
      params,
    }),
};
