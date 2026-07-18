import { create } from "zustand";
import { portfolioApi, type CreatePortfolioInput } from "@/api/portfolio";
import type { PortfolioSummary, Portfolio } from "./types";

interface PortfolioState {
  list: PortfolioSummary[];
  current: Portfolio | null;
  loading: boolean;
  error: string | null;
  fetchList: () => Promise<void>;
  fetchDetail: (id: string) => Promise<void>;
  create: (input: CreatePortfolioInput) => Promise<string>;
  remove: (id: string) => Promise<void>;
  clearError: () => void;
}

export const usePortfolioStore = create<PortfolioState>((set) => ({
  list: [],
  current: null,
  loading: false,
  error: null,
  fetchList: async () => {
    set({ loading: true, error: null });
    try {
      const data = await portfolioApi.list();
      set({ list: data, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },
  fetchDetail: async (id) => {
    set({ loading: true, error: null });
    try {
      const p = await portfolioApi.get(id);
      set({ current: p, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },
  create: async (input) => {
    const p = await portfolioApi.create(input);
    set((s) => ({ list: [...s.list, {
      portfolio_id: p.portfolio_id, name: p.name, benchmark: p.benchmark,
      cash: p.cash, updated_at: p.updated_at,
    }] }));
    return p.portfolio_id;
  },
  remove: async (id) => {
    await portfolioApi.delete(id);
    set((s) => ({ list: s.list.filter((p) => p.portfolio_id !== id) }));
  },
  clearError: () => set({ error: null }),
}));