"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, Legend,
} from "recharts";
import { productsApi, scrapingApi, type Product, type PriceHistory, type PriceComparison, type CompetitorPrice } from "@/lib/api";
import { ArrowLeft, ExternalLink, RefreshCw, TrendingUp } from "lucide-react";

const positionMeta: Record<string, { label: string; color: string }> = {
  lowest:       { label: "Найнижча ціна",    color: "bg-green-100 text-green-800 border-green-200" },
  competitive:  { label: "Конкурентна ціна", color: "bg-blue-100 text-blue-800 border-blue-200" },
  above_market: { label: "Вище ринку",        color: "bg-red-100 text-red-800 border-red-200" },
};

export default function ProductDetailPage({ params }: { params: Promise<{ article: string }> }) {
  const [article, setArticle] = useState<string | null>(null);
  const [product, setProduct] = useState<Product | null>(null);
  const [history, setHistory] = useState<PriceHistory[]>([]);
  const [comparison, setComparison] = useState<PriceComparison | null>(null);
  const [competitors, setCompetitors] = useState<CompetitorPrice[]>([]);
  const [loading, setLoading] = useState(true);
  const [scraping, setScraping] = useState(false);
  const [scrapeMsg, setScrapeMsg] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    params.then((p) => setArticle(p.article));
  }, [params]);

  useEffect(() => {
    if (!article) return;
    setLoading(true);
    Promise.all([
      productsApi.get(article),
      productsApi.history(article),
      productsApi.comparison(article).catch(() => null),
      scrapingApi.competitors(article).catch(() => []),
    ]).then(([prod, hist, comp, comps]) => {
      setProduct(prod);
      setHistory([...hist].reverse()); // oldest first for chart
      setComparison(comp);
      setCompetitors(comps as CompetitorPrice[]);
    }).finally(() => setLoading(false));
  }, [article]);

  async function startScrape() {
    if (!article) return;
    setScraping(true);
    setScrapeMsg("Запуск скрапінгу...");
    try {
      const { task_id } = await scrapingApi.start(article);
      // Poll
      const poll = async () => {
        const task = await scrapingApi.pollTask(task_id);
        if (task.status === "done") {
          setScrapeMsg(`Знайдено ${task.result?.summary.total_sources ?? 0} джерел`);
          // Refresh competitors
          const comps = await scrapingApi.competitors(article);
          setCompetitors(comps);
          const comp = await productsApi.comparison(article).catch(() => null);
          setComparison(comp);
          setScraping(false);
        } else if (task.status === "error") {
          setScrapeMsg(`Помилка: ${task.error}`);
          setScraping(false);
        } else {
          setScrapeMsg(`Статус: ${task.status}...`);
          setTimeout(poll, 3000);
        }
      };
      setTimeout(poll, 3000);
    } catch (e: unknown) {
      setScrapeMsg(`Помилка: ${e instanceof Error ? e.message : String(e)}`);
      setScraping(false);
    }
  }

  if (loading) return <p className="text-slate-400 mt-8 text-center">Завантаження...</p>;
  if (!product) return <p className="text-red-500 mt-8 text-center">Товар не знайдено</p>;

  const chartData = history.map((h) => ({
    date: new Date(h.changed_at).toLocaleDateString("uk-UA", { day: "2-digit", month: "2-digit" }),
    "Наша ціна": h.price ? Number(h.price) : null,
  }));

  const pos = comparison?.price_position ? positionMeta[comparison.price_position] : null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button onClick={() => router.back()} className="p-2 hover:bg-slate-100 rounded-lg transition-colors">
          <ArrowLeft size={18} className="text-slate-500" />
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold text-slate-900 font-mono">{product.article}</h1>
            {pos && (
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium border ${pos.color}`}>
                {pos.label}
              </span>
            )}
            {!product.is_active && (
              <span className="px-2 py-0.5 bg-slate-100 text-slate-500 rounded-full text-xs">Неактивний</span>
            )}
          </div>
          <p className="text-slate-600 mt-0.5">{product.name}</p>
        </div>
        <button
          onClick={startScrape}
          disabled={scraping}
          className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-60 text-sm font-medium transition-colors shadow-sm"
        >
          <RefreshCw size={14} className={scraping ? "animate-spin" : ""} />
          {scraping ? "Скрапінг..." : "Запустити скрапінг"}
        </button>
      </div>

      {scrapeMsg && (
        <div className="p-3 bg-purple-50 border border-purple-200 rounded-lg text-sm text-purple-700">
          {scrapeMsg}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Product info */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-3">
          <h2 className="font-semibold text-slate-800">Інформація</h2>
          {[
            ["Категорія", product.category],
            ["Бренд", product.brand],
            ["Опис", product.description],
            ["Склад", product.warehouse],
          ].map(([label, val]) => val ? (
            <div key={label}>
              <p className="text-xs text-slate-500">{label}</p>
              <p className="text-sm text-slate-800">{val}</p>
            </div>
          ) : null)}
          <hr className="border-slate-100" />
          <div className="flex justify-between">
            <div>
              <p className="text-xs text-slate-500">Наша ціна</p>
              <p className="text-2xl font-bold text-slate-900">
                {product.price ? `${Number(product.price).toFixed(0)} ₴` : "—"}
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs text-slate-500">Залишок</p>
              <p className={`text-xl font-bold ${product.quantity ? "text-green-600" : "text-slate-400"}`}>
                {product.quantity ?? 0}
              </p>
            </div>
          </div>
        </div>

        {/* Market comparison */}
        {comparison && (
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-3">
            <h2 className="font-semibold text-slate-800 flex items-center gap-2">
              <TrendingUp size={16} className="text-blue-500" /> Ринок (7 днів)
            </h2>
            {[
              ["Мінімум", comparison.market_min],
              ["Середня (зважена)", comparison.market_avg],
              ["Максимум", comparison.market_max],
            ].map(([label, val]) => val !== undefined && val !== null ? (
              <div key={String(label)} className="flex justify-between">
                <span className="text-sm text-slate-500">{label}</span>
                <span className="text-sm font-medium text-slate-800">{Number(val).toFixed(0)} ₴</span>
              </div>
            ) : null)}
            {comparison.last_scraped_at && (
              <p className="text-xs text-slate-400">
                Оновлено: {new Date(comparison.last_scraped_at).toLocaleString("uk-UA")}
              </p>
            )}
          </div>
        )}

        {/* Scraping links */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-2">
          <h2 className="font-semibold text-slate-800 mb-3">Швидкі посилання</h2>
          <Link href={`/scraping?article=${product.article}`}
            className="flex items-center gap-2 text-sm text-purple-600 hover:underline">
            <RefreshCw size={14} /> Скрапінг цього артикулу
          </Link>
          <Link href={`/scraping?article=${product.article}`}
            className="flex items-center gap-2 text-sm text-green-600 hover:underline">
            <TrendingUp size={14} /> Рекомендація ціни
          </Link>
        </div>
      </div>

      {/* Price history chart */}
      {chartData.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
          <h2 className="font-semibold text-slate-800 mb-4">Динаміка ціни</h2>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} unit=" ₴" width={70} />
              <Tooltip formatter={(v) => [`${Number(v).toFixed(0)} ₴`]} />
              <Legend />
              <Line type="monotone" dataKey="Наша ціна" stroke="#3b82f6" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Competitor prices */}
      {competitors.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-5 border-b border-slate-100">
            <h2 className="font-semibold text-slate-800">Ціни конкурентів</h2>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-slate-600">Сайт</th>
                <th className="text-right px-4 py-3 font-medium text-slate-600">Ціна</th>
                <th className="text-center px-4 py-3 font-medium text-slate-600 hidden sm:table-cell">Наявність</th>
                <th className="text-center px-4 py-3 font-medium text-slate-600 hidden lg:table-cell">Вага</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {competitors.map((c) => (
                <tr key={c.domain} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium text-slate-700">{c.domain}</td>
                  <td className="px-4 py-3 text-right font-medium text-slate-900">
                    {Number(c.price).toFixed(0)} {c.currency}
                  </td>
                  <td className="px-4 py-3 text-center hidden sm:table-cell">
                    {c.in_stock === true ? (
                      <span className="text-green-600 text-xs font-medium">є</span>
                    ) : c.in_stock === false ? (
                      <span className="text-red-500 text-xs">нема</span>
                    ) : (
                      <span className="text-slate-400 text-xs">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-center hidden lg:table-cell text-xs text-slate-500">
                    {c.effective_weight ? Number(c.effective_weight).toFixed(2) : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <a href={c.url} target="_blank" rel="noopener noreferrer"
                      className="p-1.5 hover:bg-blue-50 rounded text-slate-400 hover:text-blue-600 transition-colors inline-flex">
                      <ExternalLink size={14} />
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
