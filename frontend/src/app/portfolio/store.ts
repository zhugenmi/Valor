import { create } from "zustand";
import { type CreatePortfolioInput, portfolioApi } from "@/api/portfolio";
import type { Portfolio, PortfolioAnalytics, PortfolioSummary } from "./types";

interface PortfolioState {
  list: PortfolioSummary[];
  current: Portfolio | null;
  analytics: PortfolioAnalytics | null;
  analyticsLoading: boolean;
  loading: boolean;
  error: string | null;
  fetchList: () => Promise<void>;
  fetchDetail: (id: string) => Promise<void>;
  fetchAnalytics: (id: string) => Promise<void>;
  create: (input: CreatePortfolioInput) => Promise<string>;
  remove: (id: string) => Promise<void>;
  clearError: () => void;
}

export const usePortfolioStore = create<PortfolioState>((set) => ({
  list: [],
  current: null,
  analytics: null,
  analyticsLoading: false,
  loading: false,
  error: null,
  fetchList: async () => {
    set({ loading: true, error: null });
    try {
      const res = await portfolioApi.list();
      set({ list: (res as unknown as { data: PortfolioSummary[] }).data ?? [], loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },
  fetchDetail: async (id) => {
    set({ loading: true, error: null });
    try {
      const [pRes, aRes] = await Promise.all([
        portfolioApi.get(id),
        portfolioApi.analytics(id).catch(() => null),
      ]);
      const p = (pRes as unknown as { data: Portfolio }).data ?? null;
      const a = aRes ? (aRes as unknown as { data: PortfolioAnalytics }).data ?? null : null;
      set({ current: p, analytics: a, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },
  fetchAnalytics: async (id) => {
    set({ analyticsLoading: true });
    try {
      const res = await portfolioApi.analytics(id);
      set({ analytics: (res as unknown as { data: PortfolioAnalytics }).data ?? null, analyticsLoading: false });
    } catch (e) {
      set({ analyticsLoading: false, error: (e as Error).message });
    }
  },
  create: async (input) => {
    const res = await portfolioApi.create(input);
    const p = (res as unknown as { data: Portfolio }).data ?? (res as Portfolio);
    set((s) => ({
      list: [
        ...s.list,
        {
          portfolio_id: p.portfolio_id,
          name: p.name,
          benchmark: p.benchmark,
          cash: p.cash,
          updated_at: p.updated_at,
        },
      ],
    }));
    return p.portfolio_id;
  },
  remove: async (id) => {
    await portfolioApi.delete(id);
    set((s) => ({ list: s.list.filter((p) => p.portfolio_id !== id) }));
  },
  clearError: () => set({ error: null }),
}));
