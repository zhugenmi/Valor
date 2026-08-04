export const AGENT_ORDER = [
  "market_data",
  "fundamentals",
  "valuation",
  "technicals",
  "capital_sentiment",
  "macro_industry",
  "bull_bear_debate",
  "risk_manager",
  "portfolio_manager",
] as const;

export const AGENT_LABEL_ZH: Record<string, string> = {
  market_data: "市场数据",
  fundamentals: "基本面",
  valuation: "估值分析",
  technicals: "技术面",
  capital_sentiment: "资金面与市场情绪",
  macro_industry: "宏观与行业环境分析",
  bull_bear_debate: "多空辩论",
  risk_manager: "风险与事件分析",
  portfolio_manager: "组合决策",
};

export const AGENT_LABEL_SHORT_ZH: Record<string, string> = {
  market_data: "市场数据",
  fundamentals: "基本面",
  valuation: "估值",
  technicals: "技术面",
  capital_sentiment: "资金情绪",
  macro_industry: "宏观行业",
  bull_bear_debate: "多空辩论",
  risk_manager: "风险管理",
  portfolio_manager: "组合决策",
};

/** Which key in state.data holds analysis output for each agent. */
export const AGENT_ANALYSIS_KEYS: Record<string, string> = {
  technicals: "technical_analysis",
  fundamentals: "fundamental_analysis",
  valuation: "valuation_analysis",
  capital_sentiment: "capital_sentiment_analysis",
  macro_industry: "macro_industry_analysis",
  risk_manager: "risk_analysis",
};

export const SUB_AGENT_KEYS: Record<string, string[]> = {
  bull_bear_debate: ["bull", "bear", "verdict"],
};

export const SUB_AGENT_LABEL_ZH: Record<string, string> = {
  "bull_bear_debate.bull": "多头论点",
  "bull_bear_debate.bear": "空头论点",
  "bull_bear_debate.verdict": "综合裁决",
};

export type AgentStatus = "pending" | "running" | "completed" | "failed";

export interface Citation {
  chunk_id: string;
  doc_id: string;
  doc_title: string;
  publish_date: string;
  vintage: string;
  page_no: number | null;
  cited_text: string;
  score?: number;
}

export interface AgentState {
  status: AgentStatus;
  output: unknown;
  error?: string;
  subStates?: Record<string, unknown>;
  citations?: Citation[];
}

export interface Decision {
  action: "buy" | "sell" | "hold";
  quantity: number;
  confidence: number;
  reasoning?: string;
  /** Current shares held before this decision. 0 means 观望 (no position). */
  current_position?: number;
}

export interface WorkflowStartedEvent {
  conversation_id: string;
  thread_id: string;
  ticker: string;
  agents: string[];
}

export interface AgentCompletedEvent {
  conversation_id: string;
  thread_id: string;
  agent: string;
  state: Record<string, unknown>;
  citations?: Citation[];
}

export interface WorkflowCompletedEvent {
  conversation_id: string;
  thread_id: string;
  final_decision: Decision | null;
}

export interface SystemFailedEvent {
  role: string;
  conversation_id: string;
  thread_id: string;
  payload: { content: string };
}
