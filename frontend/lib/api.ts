const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

// ── Products ──────────────────────────────────────────────────────────────────

export interface Product {
  id: number;
  article: string;
  name: string;
  description?: string;
  category?: string;
  brand?: string;
  price?: number;
  currency?: string;
  quantity?: number;
  warehouse?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PriceHistory {
  price: number;
  currency: string;
  quantity: number;
  changed_at: string;
  changed_by?: string;
}

export interface PriceComparison {
  article: string;
  name: string;
  our_price?: number;
  currency?: string;
  market_min?: number;
  market_max?: number;
  market_avg?: number;
  price_position?: "lowest" | "competitive" | "above_market";
  last_scraped_at?: string;
}

export const productsApi = {
  list: (params?: { q?: string; category?: string; brand?: string; active_only?: boolean; limit?: number; offset?: number }) => {
    const sp = new URLSearchParams();
    if (params?.q) sp.set("q", params.q);
    if (params?.category) sp.set("category", params.category);
    if (params?.brand) sp.set("brand", params.brand);
    if (params?.active_only !== undefined) sp.set("active_only", String(params.active_only));
    if (params?.limit !== undefined) sp.set("limit", String(params.limit));
    if (params?.offset !== undefined) sp.set("offset", String(params.offset));
    return req<Product[]>(`/products?${sp}`);
  },

  get: (article: string) => req<Product>(`/products/${article}`),

  create: (body: { article: string; name: string; category?: string; brand?: string; description?: string }) =>
    req<{ id: number; article: string }>("/products", { method: "POST", body: JSON.stringify(body) }),

  update: (article: string, body: Partial<Pick<Product, "name" | "description" | "is_active" | "category" | "brand">>) =>
    req<{ ok: boolean }>(`/products/${article}`, { method: "PUT", body: JSON.stringify(body) }),

  setStock: (article: string, body: { price?: number; quantity: number; currency?: string; warehouse?: string }) =>
    req<{ ok: boolean }>(`/products/${article}/stock`, { method: "POST", body: JSON.stringify(body) }),

  activate: (article: string) =>
    req<{ ok: boolean }>(`/products/${article}/activate`, { method: "POST" }),

  deactivate: (article: string) =>
    req<{ ok: boolean }>(`/products/${article}`, { method: "DELETE" }),

  hardDelete: (article: string) =>
    req<{ ok: boolean }>(`/products/${article}/hard`, { method: "DELETE" }),

  history: (article: string) => req<PriceHistory[]>(`/products/${article}/history`),

  comparison: (article: string) => req<PriceComparison>(`/products/${article}/comparison`),

  comparisonAll: () => req<PriceComparison[]>("/products/comparison"),
};

// ── Scraping ───────────────────────────────────────────────────────────────────

export interface ScrapingTask {
  status: "pending" | "running" | "done" | "error";
  article: string;
  result?: ScrapingResult;
  error?: string;
}

export interface ScrapingResult {
  article: string;
  scraped_at: string;
  sources: SourceRecord[];
  errors: { domain: string; reason: string }[];
  summary: {
    total_sources: number;
    in_stock_count: number;
    min_price?: number;
    max_price?: number;
    median_price?: number;
    weighted_avg_price?: number;
  };
}

export interface SourceRecord {
  domain: string;
  url: string;
  price: number;
  currency: string;
  in_stock?: boolean;
  confidence: number;
  source_weight: number;
  effective_weight: number;
  parser_source: string;
  title?: string;
  raw_price?: string;
  scraped_at: string;
}

export interface ScrapingSession {
  id: number;
  article: string;
  scraped_at: string;
  sources_found: number;
  errors_count: number;
  weighted_avg?: number;
  min_price?: number;
  max_price?: number;
  median_price?: number;
}

export interface CompetitorPrice {
  article: string;
  domain: string;
  price: number;
  currency: string;
  in_stock?: boolean;
  effective_weight?: number;
  parser_source?: string;
  url: string;
  scraped_at: string;
}

export interface BatchScrapingTask {
  status: "pending" | "running" | "done" | "error";
  articles: string[];
  total: number;
  done: number;
  current: string | null;
  results: Record<string, ScrapingResult>;
  errors: Record<string, string>;
  error: string | null;
}

export const scrapingApi = {
  start: (article: string, body?: { concurrency?: number; search_limit?: number }) =>
    req<{ task_id: string; article: string }>(`/scrape/${article}`, {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    }),

  startBatch: (articles: string[], opts?: { concurrency?: number; search_limit?: number }) =>
    req<{ task_id: string; articles: string[]; total: number }>("/scrape/batch", {
      method: "POST",
      body: JSON.stringify({ articles, ...opts }),
    }),

  pollTask: (taskId: string) => req<ScrapingTask>(`/scrape/tasks/${taskId}`),

  pollBatchTask: (taskId: string) => req<BatchScrapingTask>(`/scrape/tasks/${taskId}`),

  latestSession: (article: string) => req<ScrapingSession>(`/scrape/${article}/latest`),

  sessions: (article: string, limit = 30) =>
    req<ScrapingSession[]>(`/scrape/${article}/sessions?limit=${limit}`),

  competitors: (article: string) => req<CompetitorPrice[]>(`/scrape/${article}/competitors`),
};

// ── Recommendations ────────────────────────────────────────────────────────────

export interface RecommendTask {
  status: "pending" | "running" | "done" | "error";
  article: string;
  result?: RecommendResult;
  error?: string;
}

export interface RecommendResult {
  article: string;
  recommendation: {
    price?: number;
    delta?: number;
    strategy?: string;
    confidence: number;
    reasoning: string;
  };
  market: { min?: number; median?: number; max?: number; wap?: number };
  fuzzy: { market_position?: number; own_adjustment?: number; final_position?: number };
  own_conditions: { stock_level: number; demand_velocity: number; auto_calculated?: boolean };
  competitors: {
    domain: string;
    price: number;
    currency: string;
    in_stock?: boolean;
    url: string;
    title?: string;
    effective_weight: number;
  }[];
  scraped_at: string;
  summary: { total_sources: number; min_price?: number; max_price?: number; weighted_avg_price?: number };
}

export const recommendApi = {
  start: (article: string, body?: { own_stock_level?: number; demand_velocity?: number; current_price?: number }) =>
    req<{ task_id: string; article: string }>(`/recommend/${article}`, {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    }),
  pollTask: (taskId: string) => req<RecommendTask>(`/recommend/tasks/${taskId}`),

  fromSources: (body: {
    article: string;
    sources: SourceRecord[];
    own_stock_level?: number;
    demand_velocity?: number;
    current_price?: number;
  }) =>
    req<RecommendResult>("/recommend/from-sources", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

// ── Stats ──────────────────────────────────────────────────────────────────────

export interface DashboardStats {
  total_products: number;
  total_sessions: number;
  total_sources: number;
  avg_market_price_7d?: number;
  recent_sessions: ScrapingSession[];
  price_positions: { price_position: string; count: number }[];
}

export interface CompetitorSource {
  domain: string;
  appearances: number;
  hits: number;
  weight: number;
  last_seen?: string;
}

export const statsApi = {
  dashboard: () => req<DashboardStats>("/stats/dashboard"),
  sources: (limit = 20) => req<CompetitorSource[]>(`/stats/sources?limit=${limit}`),
  categories: () => req<{ slug: string; name: string }[]>("/stats/categories"),
  brands: () => req<string[]>("/stats/brands"),
};

// ── Analytics ──────────────────────────────────────────────────────────────────

export interface MonthlySales {
  month: string;
  total_units: number;
  total_revenue: number;
  products_sold: number;
}

export interface ProductSales {
  article: string;
  name: string;
  category?: string;
  total_units: number;
  total_revenue: number;
}

export interface SeasonalityRow {
  category: string;
  month: number;
  total_units: number;
}

export interface StockStatus {
  article: string;
  name: string;
  category?: string;
  current_stock: number;
  price: number;
  monthly_forecast: number;
  months_of_supply: number | null;
}

export const analyticsApi = {
  monthlySales: (months = 12) =>
    req<MonthlySales[]>(`/analytics/sales/monthly?months=${months}`),
  topSellers: (limit = 20) =>
    req<ProductSales[]>(`/analytics/sales/top?limit=${limit}`),
  seasonality: () =>
    req<SeasonalityRow[]>("/analytics/sales/seasonality"),
  stock: () =>
    req<StockStatus[]>("/analytics/stock"),
  articleDaily: (article: string, days = 90) =>
    req<{ date: string; units: number; revenue: number }[]>(
      `/analytics/sales/daily/${article}?days=${days}`
    ),
};
