import { create } from "zustand";
import { kbApi, type KBDocListItem, type KBListParams } from "@/api/knowledge";

interface KnowledgeState {
  documents: KBDocListItem[];
  total: number;
  loading: boolean;
  error: string | null;
  selectedDocId: string | null;
  lastParams: KBListParams | undefined;
  fetchDocuments: (params?: KBListParams) => Promise<void>;
  setSelectedDoc: (docId: string | null) => void;
  clearError: () => void;
}

export const useKnowledgeStore = create<KnowledgeState>((set) => ({
  documents: [],
  total: 0,
  loading: false,
  error: null,
  selectedDocId: null,
  lastParams: undefined,
  fetchDocuments: async (params) => {
    set({ loading: true, error: null, lastParams: params });
    try {
      const res = await kbApi.list(params);
      set({
        documents: res.data?.items ?? [],
        total: res.data?.total ?? 0,
        loading: false,
      });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },
  setSelectedDoc: (docId) => set({ selectedDocId: docId }),
  clearError: () => set({ error: null }),
}));
