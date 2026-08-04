import { apiClient, type ApiResponse } from "@/lib/api-client";

export interface KBDocListItem {
  doc_id: string;
  title: string;
  category: string;
  sub_type: string;
  mime_type: string;
  file_size?: number | null;
  page_count?: number | null;
  publish_date: string | null;
  effective_until: string | null;
  vintage: string | null;
  ticker: string | null;
  chunk_count: number | null;
  chunk_strategy?: string | null;
  uploaded_at: string;
  status: string;
  source?: string | null;
  error_msg?: string | null;
}

export interface KBChunk {
  chunk_id: string;
  doc_id: string;
  seq: number;
  text: string;
  page_no: number | null;
  heading_path: string | null;
  token_count: number | null;
}

export interface KBCorrection {
  correction_id: string;
  ticker: string;
  report_period: string;
  field_name: string;
  original_value: string | null;
  corrected_value: string;
  unit: string | null;
  source_doc_id: string;
  source_page: number | null;
  corrected_at: string;
  reason: string | null;
}

export interface KBCategoryItem {
  name: string;
  display_name: string;
}

export interface KBCategory {
  research: KBCategoryItem[];
  disclosure: KBCategoryItem[];
  general: KBCategoryItem[];
  regulatory: KBCategoryItem[];
  [key: string]: KBCategoryItem[];
}

export interface KBSearchResult {
  query: string;
  chunks: (KBChunk & { score?: number })[];
}

export interface KBListParams {
  category?: string;
  sub_type?: string;
  ticker?: string;
  limit?: number;
  offset?: number;
}

const BASE = "/kb";

function buildQS(params?: Record<string, string | number | undefined>): string {
  if (!params) return "";
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  if (!entries.length) return "";
  const usp = new URLSearchParams();
  for (const [k, v] of entries) usp.set(k, String(v));
  return `?${usp.toString()}`;
}

export const kbApi = {
  list: (params?: KBListParams) =>
    apiClient.get<ApiResponse<{ items: KBDocListItem[]; total: number }>>(
      `${BASE}/documents${buildQS(params as Record<string, string | number | undefined> | undefined)}`,
    ),
  detail: (docId: string) =>
    apiClient.get<ApiResponse<KBDocListItem>>(`${BASE}/documents/${docId}`),
  chunks: (docId: string) =>
    apiClient.get<ApiResponse<KBChunk[]>>(`${BASE}/documents/${docId}/chunks`),
  corrections: (docId: string) =>
    apiClient.get<ApiResponse<KBCorrection[]>>(
      `${BASE}/documents/${docId}/corrections`,
    ),
  delete: (docId: string) =>
    apiClient.delete<ApiResponse<{ doc_id: string; deleted: boolean }>>(
      `${BASE}/documents/${docId}`,
    ),
  reindex: (docId: string, strategyName?: string) =>
    apiClient.post<
      ApiResponse<{ doc_id: string; chunk_count: number; status: string }>
    >(`${BASE}/documents/${docId}/reindex${buildQS({ strategy_name: strategyName })}`, undefined),
  categories: () =>
    apiClient.get<ApiResponse<KBCategory>>(`${BASE}/categories`),
  search: (query: string, topK = 5) =>
    apiClient.post<ApiResponse<KBSearchResult>>(`${BASE}/search`, {
      query,
      top_k: topK,
    }),
  revokeCorrection: (correctionId: string) =>
    apiClient.delete<
      ApiResponse<{ correction_id: string; deleted: boolean }>
    >(`${BASE}/corrections/${correctionId}`),
  upload: (formData: FormData) =>
    apiClient.upload<ApiResponse<{ doc_id: string; status: string }>>(
      `${BASE}/documents`,
      formData,
    ),
};
