export interface Lot {
  lot_id: string;
  open_date: string;
  quantity: number;
  cost_price: string;
  fees: string;
  note?: string | null;
}

export interface Holding {
  ticker: string;
  name?: string | null;
  lots: Lot[];
  side: "long" | "short";
}

export interface Strategy {
  strategy_id: string;
  name: string;
  method: "equal_weight" | "mean_variance" | "risk_parity";
  target_weights: Record<string, number>;
  expected_return?: number | null;
  expected_volatility?: number | null;
  rationale: string;
  created_at: string;
  params: Record<string, unknown>;
}

export interface Portfolio {
  portfolio_id: string;
  name: string;
  benchmark: string;
  cash: string;
  holdings: Holding[];
  strategies: Strategy[];
  created_at: string;
  updated_at: string;
  meta: Record<string, unknown>;
}

export interface PortfolioSummary {
  portfolio_id: string;
  name: string;
  benchmark: string;
  cash: string;
  updated_at: string;
}

export interface PositionMetric {
  ticker: string;
  name?: string | null;
  quantity: number;
  cost_price: string;
  current_price: string;
  market_value: string;
  cost_value: string;
  unrealized_pnl: string;
  unrealized_pnl_pct: number;
  weight: number;
  sector?: string | null;
  beta?: number | null;
}

export interface ConcentrationMetrics {
  top1_weight: number;
  top5_weight: number;
  herfindahl_index: number;
  num_holdings: number;
  effective_holdings: number;
}

export interface PortfolioAnalytics {
  portfolio_id: string;
  as_of: string;
  total_market_value: string;
  total_cost_value: string;
  cash: string;
  total_assets: string;
  total_unrealized_pnl: string;
  total_unrealized_pnl_pct: number;
  positions: PositionMetric[];
  sector_exposure: Record<string, number>;
  concentration: ConcentrationMetrics;
  benchmark?: string | null;
  portfolio_beta?: number | null;
}

export interface RebalanceAction {
  ticker: string;
  side: "buy" | "sell";
  target_quantity: number;
  delta_quantity: number;
  target_weight: number;
  current_weight: number;
  est_cost: string;
  rationale: string;
}

export interface FundTransfer {
  from_portfolio_id: string;
  to_portfolio_id: string;
  amount: string;
  rationale: string;
}

export interface RebalancePlan {
  portfolio_id: string;
  strategy_id: string;
  actions: RebalanceAction[];
  total_est_cost: string;
  cash_before: string;
  cash_after: string;
  fund_transfers: FundTransfer[];
  warnings: string[];
  created_at: string;
}

export interface ImportResult {
  format: string;
  imported_rows: number;
  total_rows: number;
  errors: Array<{ row: number; reason: string }>;
  holdings_count: number;
}
