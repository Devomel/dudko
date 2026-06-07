"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import {
  scrapingApi, productsApi, recommendApi,
  type BatchScrapingTask, type Product,
  type SourceRecord, type RecommendResult,
} from "@/lib/api";
import {
  Search, ExternalLink, Activity, CheckSquare, X,
  ChevronRight, Bot, RotateCcw, Check, AlertCircle,
  Loader2, Sparkles,
} from "lucide-react";

// ── Step indicator ─────────────────────────────────────────────────────────────
const STEPS = [
  { id: "select",   label: "Артикули" },
  { id: "scraping", label: "Скрапінг" },
  { id: "review",   label: "Джерела" },
  { id: "results",  label: "Рекомендації" },
] as const;
type Step = (typeof STEPS)[number]["id"];

function StepBar({ current }: { current: Step }) {
  const idx = STEPS.findIndex((s) => s.id === current);
  return (
    <div className="flex items-center gap-0 flex-wrap gap-y-2">
      {STEPS.map((s, i) => (
        <div key={s.id} className="flex items-center">
          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium ${
            s.id === current
              ? "bg-purple-600 text-white"
              : i < idx
              ? "bg-purple-100 text-purple-700"
              : "bg-slate-100 text-slate-400"
          }`}>
            <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-bold ${
              i < idx ? "bg-purple-600 text-white" : ""
            }`}>
              {i < idx ? <Check size={9} /> : i + 1}
            </span>
            {s.label}
          </div>
          {i < STEPS.length - 1 && (
            <ChevronRight size={14} className={i < idx ? "text-purple-400" : "text-slate-300"} />
          )}
        </div>
      ))}
    </div>
  );
}

const SESSION_KEY = "scraping_session";

// ── Main page ─────────────────────────────────────────────────────────────────
function PriceCheckContent() {
  const [step, setStep] = useState<Step>("select");
  const [products, setProducts] = useState<Product[]>([]);
  const [filter, setFilter] = useState("");
  const [selectedArticles, setSelectedArticles] = useState<Set<string>>(new Set());

  // Step 2
  const [batchTask, setBatchTask] = useState<BatchScrapingTask | null>(null);
  const [scrapingStatus, setScrapingStatus] = useState("");

  // Step 3: article → selected domain set
  const [selectedSources, setSelectedSources] = useState<Record<string, Set<string>>>({});

  // Step 4
  const [recommendations, setRecommendations] = useState<
    Record<string, { result?: RecommendResult; error?: string }>
  >({});
  const [recLoading, setRecLoading] = useState(false);

  // Step 4: price editing per article
  const [priceInputs, setPriceInputs] = useState<Record<string, string>>({});
  const [priceSave, setPriceSave] = useState<Record<string, "idle" | "saving" | "saved" | "error">>({});

  // Restore session from sessionStorage on mount
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(SESSION_KEY);
      if (!raw) return;
      const { articles, task, sources } = JSON.parse(raw) as {
        articles: string[];
        task: BatchScrapingTask;
        sources: Record<string, string[]>;
      };
      setSelectedArticles(new Set(articles));
      setBatchTask(task);
      const restored: Record<string, Set<string>> = {};
      for (const [art, domains] of Object.entries(sources)) {
        restored[art] = new Set(domains);
      }
      setSelectedSources(restored);
      setStep("review");
    } catch {}
  }, []);

  // Persist completed batch task to sessionStorage
  useEffect(() => {
    if (batchTask?.status !== "done") return;
    try {
      const sources: Record<string, string[]> = {};
      for (const [art, set] of Object.entries(selectedSources)) {
        sources[art] = Array.from(set);
      }
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({
        articles: Array.from(selectedArticles),
        task: batchTask,
        sources,
      }));
    } catch {}
  }, [batchTask, selectedArticles, selectedSources]);

  useEffect(() => {
    productsApi.list({ active_only: true, limit: 500 }).then(setProducts).catch(() => {});
  }, []);

  const visible = products.filter(
    (p) =>
      !filter ||
      p.article.toLowerCase().includes(filter.toLowerCase()) ||
      p.name.toLowerCase().includes(filter.toLowerCase())
  );

  function toggleArticle(article: string) {
    setSelectedArticles((prev) => {
      const next = new Set(prev);
      next.has(article) ? next.delete(article) : next.add(article);
      return next;
    });
  }

  // ── Step 1 → 2 ────────────────────────────────────────────────────────────
  async function startScraping() {
    if (selectedArticles.size === 0) return;
    setBatchTask(null);
    setScrapingStatus("Запуск скрапінгу...");
    setStep("scraping");

    try {
      const { task_id } = await scrapingApi.startBatch(
        Array.from(selectedArticles),
        { concurrency: 3 }
      );

      const poll = async () => {
        const t = await scrapingApi.pollBatchTask(task_id);
        setBatchTask(t);
        if (t.status === "done") {
          setScrapingStatus("");
          // Pre-select all sources
          const init: Record<string, Set<string>> = {};
          for (const [art, res] of Object.entries(t.results)) {
            init[art] = new Set(res.sources.map((s) => s.domain));
          }
          setSelectedSources(init);
        } else if (t.status === "error") {
          setScrapingStatus(`Помилка: ${t.error}`);
        } else {
          const cur = t.current ? ` — ${t.current}` : "";
          setScrapingStatus(`${t.done}/${t.total} артикулів${cur}`);
          setTimeout(poll, 3000);
        }
      };
      setTimeout(poll, 2000);
    } catch (e) {
      setScrapingStatus(`Помилка: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  // ── Step 3 → 4 ────────────────────────────────────────────────────────────
  async function runRecommendations() {
    if (!batchTask) return;
    setRecLoading(true);
    setRecommendations({});
    setStep("results");

    const articles = Array.from(selectedArticles).filter((art) => {
      const sel = selectedSources[art];
      return sel && sel.size > 0 && batchTask.results[art];
    });

    const out: Record<string, { result?: RecommendResult; error?: string }> = {};

    await Promise.allSettled(
      articles.map(async (art) => {
        const chosen = batchTask.results[art].sources.filter((s) =>
          selectedSources[art]?.has(s.domain)
        );
        const product = products.find((p) => p.article === art);
        try {
          const result = await recommendApi.fromSources({
            article: art,
            sources: chosen,
            current_price: product?.price ?? undefined,
          });
          out[art] = { result };
        } catch (e) {
          out[art] = { error: e instanceof Error ? e.message : String(e) };
        }
      })
    );

    setRecommendations(out);
    setRecLoading(false);

    // Pre-fill price inputs with recommended prices
    const inputs: Record<string, string> = {};
    for (const [art, rec] of Object.entries(out)) {
      const price = rec.result?.recommendation.price;
      if (price != null) inputs[art] = String(Math.round(price));
    }
    setPriceInputs(inputs);
    setPriceSave({});
  }

  async function savePrice(art: string) {
    const price = parseFloat(priceInputs[art] ?? "");
    if (!price || price <= 0) return;
    const product = products.find((p) => p.article === art);
    setPriceSave((prev) => ({ ...prev, [art]: "saving" }));
    try {
      await productsApi.setStock(art, { price, quantity: product?.quantity ?? 0 });
      setPriceSave((prev) => ({ ...prev, [art]: "saved" }));
    } catch {
      setPriceSave((prev) => ({ ...prev, [art]: "error" }));
    }
  }

  function toggleSource(article: string, domain: string) {
    setSelectedSources((prev) => {
      const set = new Set(prev[article] ?? []);
      set.has(domain) ? set.delete(domain) : set.add(domain);
      return { ...prev, [article]: set };
    });
  }

  function toggleAllForArticle(article: string, sources: SourceRecord[]) {
    setSelectedSources((prev) => {
      const set = prev[article] ?? new Set<string>();
      const allOn = sources.every((s) => set.has(s.domain));
      return {
        ...prev,
        [article]: allOn ? new Set() : new Set(sources.map((s) => s.domain)),
      };
    });
  }

  const totalSelectedSources = Array.from(selectedArticles).reduce(
    (acc, art) => acc + (selectedSources[art]?.size ?? 0),
    0
  );

  function reset() {
    sessionStorage.removeItem(SESSION_KEY);
    setStep("select");
    setBatchTask(null);
    setRecommendations({});
    setScrapingStatus("");
    setSelectedArticles(new Set());
    setSelectedSources({});
    setPriceInputs({});
    setPriceSave({});
  }

  // ═══════════════════════════════════════════════════════════════════════════
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Перевірка цін конкурентів</h1>
          <p className="text-slate-500 mt-1">
            Скрапінг → AI-парсинг → вибір джерел → нечітка логіка → рекомендована ціна
          </p>
        </div>
        {step !== "select" && (
          <button
            onClick={reset}
            className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50"
          >
            <RotateCcw size={13} /> Почати знову
          </button>
        )}
      </div>

      <StepBar current={step} />

      {/* ── STEP 1: Вибір артикулів ──────────────────────────────────────── */}
      {step === "select" && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
          <div className="p-5 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="Пошук по артикулу або назві..."
                  className="w-full pl-8 pr-3 py-1.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                />
              </div>
              <button
                onClick={() => setSelectedArticles(new Set(visible.map((p) => p.article)))}
                className="flex items-center gap-1 px-3 py-1.5 text-xs text-slate-600 border border-slate-300 rounded-lg hover:bg-slate-50 whitespace-nowrap"
              >
                <CheckSquare size={13} /> Всі
              </button>
              <button
                onClick={() => setSelectedArticles(new Set())}
                className="flex items-center gap-1 px-3 py-1.5 text-xs text-slate-600 border border-slate-300 rounded-lg hover:bg-slate-50 whitespace-nowrap"
              >
                <X size={13} /> Зняти
              </button>
              <span className="text-sm text-slate-400 whitespace-nowrap">
                {selectedArticles.size} / {visible.length}
              </span>
            </div>
          </div>

          <div className="max-h-96 overflow-y-auto divide-y divide-slate-100">
            {visible.map((p) => (
              <label
                key={p.article}
                className="flex items-center gap-3 px-5 py-2.5 cursor-pointer hover:bg-slate-50 select-none"
              >
                <input
                  type="checkbox"
                  checked={selectedArticles.has(p.article)}
                  onChange={() => toggleArticle(p.article)}
                  className="rounded accent-purple-600"
                />
                <span className="font-mono text-xs text-purple-700 w-36 flex-shrink-0">
                  {p.article}
                </span>
                <span className="text-slate-700 text-sm flex-1 truncate">{p.name}</span>
                <span className="text-xs text-slate-400 whitespace-nowrap">
                  {p.price ? `${Number(p.price).toFixed(0)} ₴` : "—"}
                </span>
                {p.quantity !== undefined && (
                  <span className="text-xs text-slate-400 whitespace-nowrap">{p.quantity} шт</span>
                )}
              </label>
            ))}
            {visible.length === 0 && (
              <p className="py-8 text-center text-slate-400 text-sm">Товарів не знайдено</p>
            )}
          </div>

          <div className="p-5 border-t border-slate-100 flex items-center justify-between">
            <p className="text-sm text-slate-400">
              Ціни витягуються через AI (gpt-4o-mini). Залишки та попит беруться з БД автоматично.
            </p>
            <button
              onClick={startScraping}
              disabled={selectedArticles.size === 0}
              className="flex items-center gap-2 px-5 py-2.5 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium shadow-sm transition-colors"
            >
              <Activity size={15} />
              Скрапити {selectedArticles.size > 0 && `(${selectedArticles.size})`}
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}

      {/* ── STEP 2: Прогрес скрапінгу ────────────────────────────────────── */}
      {step === "scraping" && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
            {/* Progress bar */}
            {batchTask && batchTask.total > 0 && (
              <div className="mb-5">
                <div className="flex justify-between text-sm text-slate-600 mb-2">
                  <span>Прогрес</span>
                  <span>
                    {batchTask.done} / {batchTask.total}
                  </span>
                </div>
                <div className="w-full bg-slate-100 rounded-full h-2.5">
                  <div
                    className="bg-purple-500 h-2.5 rounded-full transition-all duration-700"
                    style={{
                      width: `${Math.round((batchTask.done / batchTask.total) * 100)}%`,
                    }}
                  />
                </div>
                {scrapingStatus && (
                  <p className="text-xs text-slate-500 mt-1.5">{scrapingStatus}</p>
                )}
              </div>
            )}

            {!batchTask && (
              <div className="flex items-center gap-3 py-4 text-slate-500">
                <Loader2 size={18} className="animate-spin text-purple-500" />
                <span className="text-sm">{scrapingStatus || "Запуск..."}</span>
              </div>
            )}

            {/* Per-article status list */}
            <div className="divide-y divide-slate-100 rounded-lg border border-slate-200 overflow-hidden">
              {Array.from(selectedArticles).map((art) => {
                const res = batchTask?.results[art];
                const err = batchTask?.errors[art];
                const isCurrent = batchTask?.current === art;
                return (
                  <div key={art} className="flex items-center gap-3 px-4 py-2.5">
                    <div className="w-5 flex-shrink-0 flex items-center justify-center">
                      {res ? (
                        <Check size={15} className="text-green-500" />
                      ) : err ? (
                        <AlertCircle size={15} className="text-red-400" />
                      ) : isCurrent ? (
                        <Loader2 size={15} className="animate-spin text-purple-500" />
                      ) : (
                        <div className="w-3 h-3 rounded-full border-2 border-slate-300" />
                      )}
                    </div>
                    <span className="font-mono text-xs text-purple-700 w-36 flex-shrink-0">
                      {art}
                    </span>
                    <span className="text-sm text-slate-600 flex-1">
                      {res ? (
                        <span className="text-green-700 font-medium">
                          {res.sources.length} джерел знайдено
                        </span>
                      ) : err ? (
                        <span className="text-red-500 text-xs">{err}</span>
                      ) : isCurrent ? (
                        <span className="text-purple-600 text-xs">
                          Скрапінг + AI парсинг...
                        </span>
                      ) : (
                        <span className="text-slate-400 text-xs">В черзі</span>
                      )}
                    </span>
                    {res && (
                      <span className="flex items-center gap-1 text-xs text-slate-400">
                        <Bot size={11} /> AI
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {batchTask?.status === "done" && (
            <div className="flex justify-end">
              <button
                onClick={() => setStep("review")}
                className="flex items-center gap-2 px-5 py-2.5 bg-purple-600 text-white rounded-lg hover:bg-purple-700 text-sm font-medium shadow-sm"
              >
                Переглянути джерела <ChevronRight size={14} />
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── STEP 3: Вибір довірених джерел ───────────────────────────────── */}
      {step === "review" && batchTask && (
        <div className="space-y-4">
          <p className="text-sm text-slate-600 bg-blue-50 border border-blue-100 rounded-lg px-4 py-2.5">
            Відмітьте джерела, яким ви довіряєте. Нечітка логіка рахуватиме ціну лише на основі вибраних.
          </p>

          {Array.from(selectedArticles).map((art) => {
            const res = batchTask.results[art];
            const err = batchTask.errors[art];
            const product = products.find((p) => p.article === art);
            const srcs = (res?.sources ?? []).slice().sort((a, b) => a.price - b.price);
            const artSel = selectedSources[art] ?? new Set<string>();
            const allChecked = srcs.length > 0 && srcs.every((s) => artSel.has(s.domain));

            return (
              <div
                key={art}
                className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden"
              >
                {/* Article header */}
                <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-100 bg-slate-50">
                  <span className="font-mono text-sm font-semibold text-purple-700">{art}</span>
                  {product && (
                    <span className="text-sm text-slate-600 truncate">{product.name}</span>
                  )}
                  <div className="ml-auto flex items-center gap-3">
                    <span className="text-xs text-slate-400">
                      {artSel.size} / {srcs.length} вибрано
                    </span>
                    {srcs.length > 0 && (
                      <button
                        onClick={() => toggleAllForArticle(art, srcs)}
                        className="text-xs text-purple-600 hover:underline"
                      >
                        {allChecked ? "Зняти всі" : "Вибрати всі"}
                      </button>
                    )}
                  </div>
                </div>

                {err && (
                  <div className="px-5 py-3 flex items-center gap-2 text-red-600 text-sm">
                    <AlertCircle size={14} /> Помилка: {err}
                  </div>
                )}
                {!err && srcs.length === 0 && (
                  <p className="px-5 py-3 text-sm text-slate-400">Ціни не знайдено</p>
                )}

                {srcs.length > 0 && (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-100 text-xs">
                        <th className="w-10 px-4 py-2" />
                        <th className="text-left px-4 py-2 font-medium text-slate-500">Магазин</th>
                        <th className="text-right px-4 py-2 font-medium text-slate-500">Ціна</th>
                        <th className="text-center px-4 py-2 font-medium text-slate-500 hidden sm:table-cell">
                          Наявність
                        </th>
                        <th className="text-center px-4 py-2 font-medium text-slate-500 hidden md:table-cell">
                          Метод
                        </th>
                        <th className="text-right px-4 py-2 font-medium text-slate-500 hidden lg:table-cell">
                          Вага
                        </th>
                        <th className="px-4 py-2" />
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {srcs.map((s) => {
                        const checked = artSel.has(s.domain);
                        return (
                          <tr
                            key={s.domain}
                            className={`cursor-pointer transition-colors ${
                              checked ? "hover:bg-slate-50" : "opacity-50 bg-slate-50"
                            }`}
                            onClick={() => toggleSource(art, s.domain)}
                          >
                            <td className="px-4 py-2.5">
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleSource(art, s.domain)}
                                onClick={(e) => e.stopPropagation()}
                                className="rounded accent-purple-600"
                              />
                            </td>
                            <td className="px-4 py-2.5">
                              <div className="font-medium text-slate-700">{s.domain}</div>
                              {s.title && (
                                <div className="text-xs text-slate-400 truncate max-w-xs">
                                  {s.title}
                                </div>
                              )}
                            </td>
                            <td className="px-4 py-2.5 text-right font-bold text-slate-900">
                              {s.price.toFixed(0)} {s.currency}
                            </td>
                            <td className="px-4 py-2.5 text-center hidden sm:table-cell text-xs">
                              {s.in_stock === true ? (
                                <span className="text-green-600 font-medium">✓ є</span>
                              ) : s.in_stock === false ? (
                                <span className="text-red-500">✗ нема</span>
                              ) : (
                                "—"
                              )}
                            </td>
                            <td className="px-4 py-2.5 text-center hidden md:table-cell">
                              {s.parser_source === "ai" ? (
                                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-purple-50 text-purple-700 rounded text-xs font-medium">
                                  <Bot size={10} /> AI
                                </span>
                              ) : (
                                <span className="px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded text-xs">
                                  {s.parser_source}
                                </span>
                              )}
                            </td>
                            <td className="px-4 py-2.5 text-right hidden lg:table-cell">
                              <span
                                className={`text-xs font-medium ${
                                  s.effective_weight >= 0.6
                                    ? "text-green-600"
                                    : s.effective_weight >= 0.3
                                    ? "text-blue-600"
                                    : "text-slate-400"
                                }`}
                              >
                                {s.effective_weight.toFixed(2)}
                              </span>
                            </td>
                            <td className="px-4 py-2.5">
                              <a
                                href={s.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="p-1.5 hover:bg-blue-50 rounded text-slate-400 hover:text-blue-600 inline-flex"
                              >
                                <ExternalLink size={13} />
                              </a>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            );
          })}

          <div className="flex items-center justify-between">
            <button
              onClick={() => setStep("scraping")}
              className="text-sm text-slate-500 hover:text-slate-800 px-4 py-2 border border-slate-200 rounded-lg hover:bg-slate-50"
            >
              ← Назад
            </button>
            <button
              onClick={runRecommendations}
              disabled={totalSelectedSources === 0}
              className="flex items-center gap-2 px-6 py-2.5 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium shadow-sm"
            >
              <Sparkles size={15} />
              Нечітка логіка ({totalSelectedSources}{" "}
              {totalSelectedSources === 1 ? "джерело" : "джерел"})
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}

      {/* ── STEP 4: Рекомендації ──────────────────────────────────────────── */}
      {step === "results" && (
        <div className="space-y-4">
          {recLoading && (
            <div className="flex items-center justify-center gap-3 py-16 text-slate-500">
              <Loader2 size={22} className="animate-spin text-purple-500" />
              <span>Обчислення нечіткої логіки...</span>
            </div>
          )}

          {!recLoading &&
            Array.from(selectedArticles).map((art) => {
              const rec = recommendations[art];
              if (!rec) return null;
              const product = products.find((p) => p.article === art);

              if (rec.error) {
                return (
                  <div
                    key={art}
                    className="bg-white rounded-xl border border-red-200 shadow-sm p-5"
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className="font-mono text-sm text-purple-700">{art}</span>
                      {product && (
                        <span className="text-sm text-slate-500">{product.name}</span>
                      )}
                    </div>
                    <p className="text-sm text-red-600 flex items-center gap-1.5">
                      <AlertCircle size={14} /> {rec.error}
                    </p>
                  </div>
                );
              }

              const r = rec.result!;
              const recPrice = r.recommendation.price;
              const currPrice = product?.price;
              const delta =
                recPrice != null && currPrice != null ? recPrice - currPrice : null;

              return (
                <div
                  key={art}
                  className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden"
                >
                  {/* Article header */}
                  <div className="px-5 py-3 border-b border-slate-100 bg-slate-50 flex items-center gap-3">
                    <span className="font-mono text-sm font-semibold text-purple-700">{art}</span>
                    {product && (
                      <span className="text-sm text-slate-600 truncate">{product.name}</span>
                    )}
                    {currPrice != null && (
                      <span className="ml-auto text-xs text-slate-400">
                        Поточна: {currPrice.toFixed(0)} ₴
                      </span>
                    )}
                    <Link
                      href={`/products/${art}`}
                      className="text-xs text-blue-600 hover:underline ml-2"
                    >
                      Деталі →
                    </Link>
                  </div>

                  <div className="p-5 grid grid-cols-1 md:grid-cols-3 gap-6">
                    {/* Recommended price */}
                    <div>
                      <div className="text-xs text-slate-400 uppercase tracking-wide font-medium mb-2">
                        Рекомендована ціна
                      </div>
                      {recPrice != null ? (
                        <>
                          <div className="text-4xl font-bold text-slate-900">
                            {recPrice.toFixed(0)}{" "}
                            <span className="text-2xl text-slate-400">₴</span>
                          </div>
                          {delta !== null && (
                            <div
                              className={`text-sm mt-1 font-medium ${
                                delta > 0
                                  ? "text-green-600"
                                  : delta < 0
                                  ? "text-red-500"
                                  : "text-slate-400"
                              }`}
                            >
                              {delta > 0 ? "+" : ""}
                              {delta.toFixed(0)} ₴ від поточної
                            </div>
                          )}
                        </>
                      ) : (
                        <div className="text-slate-400 text-2xl">—</div>
                      )}
                      <div className="mt-3 flex flex-wrap gap-2">
                        {r.recommendation.strategy && (
                          <span className="px-2 py-0.5 bg-purple-50 text-purple-700 text-xs rounded-full font-medium">
                            {r.recommendation.strategy}
                          </span>
                        )}
                        <span
                          className={`px-2 py-0.5 text-xs rounded-full font-medium ${
                            r.recommendation.confidence >= 0.6
                              ? "bg-green-50 text-green-700"
                              : r.recommendation.confidence >= 0.3
                              ? "bg-yellow-50 text-yellow-700"
                              : "bg-slate-100 text-slate-500"
                          }`}
                        >
                          впевненість {(r.recommendation.confidence * 100).toFixed(0)}%
                        </span>
                        {r.own_conditions.auto_calculated && (
                          <span className="px-2 py-0.5 bg-blue-50 text-blue-600 text-xs rounded-full">
                            авто-параметри
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Market data */}
                    <div>
                      <div className="text-xs text-slate-400 uppercase tracking-wide font-medium mb-2">
                        Ринок ({r.summary.total_sources} джерел)
                      </div>
                      <div className="space-y-2">
                        {(
                          [
                            ["Мінімум", r.market.min],
                            ["Медіана", r.market.median],
                            ["Максимум", r.market.max],
                            ["Зважена сер.", r.market.wap],
                          ] as [string, number | undefined][]
                        ).map(([label, value]) => (
                          <div key={label} className="flex justify-between text-sm">
                            <span className="text-slate-500">{label}</span>
                            <span className="font-medium text-slate-800">
                              {value != null ? `${Number(value).toFixed(0)} ₴` : "—"}
                            </span>
                          </div>
                        ))}
                      </div>
                      <div className="mt-3 pt-3 border-t border-slate-100 space-y-1.5 text-xs text-slate-500">
                        <div className="flex justify-between">
                          <span>Залишки (норм.)</span>
                          <span>{(r.own_conditions.stock_level * 100).toFixed(0)}%</span>
                        </div>
                        <div className="flex justify-between">
                          <span>Швидкість попиту</span>
                          <span>{(r.own_conditions.demand_velocity * 100).toFixed(0)}%</span>
                        </div>
                      </div>
                    </div>

                    {/* Reasoning */}
                    <div>
                      <div className="text-xs text-slate-400 uppercase tracking-wide font-medium mb-2">
                        Обгрунтування
                      </div>
                      <p className="text-xs text-slate-600 leading-relaxed">
                        {r.recommendation.reasoning}
                      </p>
                    </div>
                  </div>

                  {/* Price update */}
                  <div className="border-t border-slate-100 px-5 py-3 flex flex-wrap items-center gap-3 bg-slate-50">
                    <span className="text-sm text-slate-600 font-medium whitespace-nowrap">Встановити ціну:</span>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        min={1}
                        value={priceInputs[art] ?? ""}
                        onChange={(e) => {
                          setPriceInputs((prev) => ({ ...prev, [art]: e.target.value }));
                          setPriceSave((prev) => ({ ...prev, [art]: "idle" }));
                        }}
                        className="w-28 px-2 py-1.5 border border-slate-300 rounded-lg text-sm text-right focus:outline-none focus:ring-2 focus:ring-green-400"
                        placeholder="ціна"
                      />
                      <span className="text-slate-400 text-sm">₴</span>
                    </div>
                    {recPrice != null && priceInputs[art] !== String(Math.round(recPrice)) && (
                      <button
                        onClick={() => setPriceInputs((prev) => ({ ...prev, [art]: String(Math.round(recPrice)) }))}
                        className="text-xs text-purple-600 hover:underline whitespace-nowrap"
                      >
                        ← рекомендована
                      </button>
                    )}
                    <button
                      onClick={() => savePrice(art)}
                      disabled={priceSave[art] === "saving" || !priceInputs[art]}
                      className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${
                        priceSave[art] === "saved"
                          ? "bg-green-100 text-green-700 border border-green-300"
                          : "bg-green-600 text-white hover:bg-green-700"
                      }`}
                    >
                      {priceSave[art] === "saving" ? "Збереження..." :
                       priceSave[art] === "saved" ? "✓ Збережено" : "Зберегти ціну"}
                    </button>
                    {priceSave[art] === "error" && (
                      <span className="text-xs text-red-500">Помилка збереження</span>
                    )}
                  </div>

                  {/* Competitors mini-table */}
                  {r.competitors.length > 0 && (
                    <div className="border-t border-slate-100">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="bg-slate-50">
                            <th className="text-left px-5 py-2 font-medium text-slate-500">
                              Магазин
                            </th>
                            <th className="text-right px-5 py-2 font-medium text-slate-500">
                              Ціна
                            </th>
                            <th className="text-center px-5 py-2 font-medium text-slate-500 hidden sm:table-cell">
                              Наявність
                            </th>
                            <th className="text-right px-5 py-2 font-medium text-slate-500 hidden md:table-cell">
                              Вага
                            </th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {r.competitors.map((c) => (
                            <tr key={c.domain} className="hover:bg-slate-50">
                              <td className="px-5 py-2">
                                <a
                                  href={c.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-blue-600 hover:underline inline-flex items-center gap-1"
                                >
                                  {c.domain} <ExternalLink size={10} />
                                </a>
                                {c.title && (
                                  <div className="text-slate-400 truncate max-w-xs">{c.title}</div>
                                )}
                              </td>
                              <td className="px-5 py-2 text-right font-semibold text-slate-800">
                                {c.price.toFixed(0)} {c.currency}
                              </td>
                              <td className="px-5 py-2 text-center hidden sm:table-cell">
                                {c.in_stock === true ? (
                                  <span className="text-green-600">✓</span>
                                ) : c.in_stock === false ? (
                                  <span className="text-red-400">✗</span>
                                ) : (
                                  "—"
                                )}
                              </td>
                              <td className="px-5 py-2 text-right hidden md:table-cell text-slate-500">
                                {c.effective_weight.toFixed(2)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              );
            })}

          {!recLoading && (
            <div className="flex justify-start">
              <button
                onClick={() => setStep("review")}
                className="text-sm text-slate-500 hover:text-slate-800 px-4 py-2 border border-slate-200 rounded-lg hover:bg-slate-50"
              >
                ← Змінити джерела
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ScrapingPage() {
  return (
    <Suspense fallback={<p className="text-slate-400 mt-8 text-center">Завантаження...</p>}>
      <PriceCheckContent />
    </Suspense>
  );
}
