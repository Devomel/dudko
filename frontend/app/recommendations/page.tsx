"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { recommendApi, type RecommendResult } from "@/lib/api";
import { TrendingUp, ExternalLink, Lightbulb, ChevronDown, ChevronUp, Database } from "lucide-react";

const strategyMeta: Record<string, { label: string; color: string }> = {
  undercut:     { label: "Нижче ринку",     color: "bg-green-100 text-green-800" },
  match:        { label: "По ринку",         color: "bg-blue-100 text-blue-800" },
  premium:      { label: "Преміум",          color: "bg-purple-100 text-purple-800" },
  penetration:  { label: "Проникнення",      color: "bg-orange-100 text-orange-800" },
  default:      { label: "Без даних",        color: "bg-slate-100 text-slate-600" },
};

function GaugeBar({ value, label, auto }: { value: number; label: string; auto?: boolean }) {
  const pct = Math.round(value * 100);
  return (
    <div>
      <div className="flex justify-between text-xs text-slate-500 mb-1">
        <span className="flex items-center gap-1">
          {label}
          {auto && (
            <span className="flex items-center gap-0.5 px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded text-[10px] font-medium">
              <Database size={9} /> авто
            </span>
          )}
        </span>
        <span>{pct}%</span>
      </div>
      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full bg-blue-500 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function ResultCard({ result, article }: { result: RecommendResult; article: string }) {
  const [showCompetitors, setShowCompetitors] = useState(false);
  const rec = result.recommendation;
  const stratMeta = rec.strategy ? (strategyMeta[rec.strategy] ?? strategyMeta.default) : strategyMeta.default;
  const isAuto = result.own_conditions.auto_calculated === true;

  return (
    <div className="space-y-4">
      {/* Main recommendation */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <p className="text-sm text-slate-500">Рекомендована ціна для</p>
            <p className="font-mono text-lg font-bold text-slate-900">{article}</p>
          </div>
          <div className="text-right">
            {rec.price ? (
              <p className="text-3xl font-bold text-blue-700">{rec.price.toFixed(0)} ₴</p>
            ) : (
              <p className="text-xl text-slate-400">Немає даних</p>
            )}
            {rec.delta !== null && rec.delta !== undefined && (
              <p className={`text-sm font-medium ${rec.delta > 0 ? "text-red-500" : rec.delta < 0 ? "text-green-600" : "text-slate-500"}`}>
                {rec.delta > 0 ? "+" : ""}{rec.delta.toFixed(0)} ₴ від поточної
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 mb-4">
          {rec.strategy && (
            <span className={`px-3 py-1 rounded-full text-xs font-medium ${stratMeta.color}`}>
              {stratMeta.label}
            </span>
          )}
          <span className={`px-3 py-1 rounded-full text-xs font-medium ${rec.confidence >= 0.7 ? "bg-green-100 text-green-700" : rec.confidence >= 0.4 ? "bg-yellow-100 text-yellow-700" : "bg-red-100 text-red-700"}`}>
            Впевненість: {(rec.confidence * 100).toFixed(0)}%
          </span>
          {isAuto && (
            <span className="flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
              <Database size={11} /> Параметри з БД
            </span>
          )}
        </div>

        {rec.reasoning && (
          <div className="flex items-start gap-2 p-3 bg-slate-50 rounded-lg">
            <Lightbulb size={16} className="text-yellow-500 mt-0.5 flex-shrink-0" />
            <p className="text-sm text-slate-700">{rec.reasoning}</p>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Market summary */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-3">
          <h3 className="font-semibold text-slate-800 flex items-center gap-2">
            <TrendingUp size={15} className="text-blue-500" /> Ринкові ціни
          </h3>
          {[
            ["Мінімум", result.market.min],
            ["Медіана", result.market.median],
            ["Максимум", result.market.max],
            ["Зважена серед.", result.market.wap],
          ].map(([label, val]) => val !== null && val !== undefined ? (
            <div key={String(label)} className="flex justify-between text-sm">
              <span className="text-slate-500">{label}</span>
              <span className="font-medium text-slate-900">{Number(val).toFixed(0)} ₴</span>
            </div>
          ) : null)}
          <p className="text-xs text-slate-400">
            Джерел: {result.summary.total_sources} • {new Date(result.scraped_at).toLocaleString("uk-UA")}
          </p>
        </div>

        {/* Fuzzy logic inputs */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-3">
          <h3 className="font-semibold text-slate-800">Нечітка логіка</h3>
          <GaugeBar value={result.own_conditions.stock_level} label="Залишок (0=мало, 1=багато)" auto={isAuto} />
          <GaugeBar value={result.own_conditions.demand_velocity} label="Попит (0=слабкий, 1=сильний)" auto={isAuto} />
          {result.fuzzy.market_position !== undefined && result.fuzzy.market_position !== null && (
            <GaugeBar value={result.fuzzy.market_position} label="Позиція на ринку" />
          )}
          {result.fuzzy.own_adjustment !== undefined && result.fuzzy.own_adjustment !== null && (
            <GaugeBar value={result.fuzzy.own_adjustment} label="Коригування" />
          )}
        </div>
      </div>

      {/* Competitors */}
      {result.competitors.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <button
            onClick={() => setShowCompetitors(!showCompetitors)}
            className="w-full flex items-center justify-between px-5 py-4 hover:bg-slate-50 transition-colors"
          >
            <span className="font-semibold text-slate-800">
              Конкуренти ({result.competitors.length})
            </span>
            {showCompetitors ? <ChevronUp size={16} className="text-slate-400" /> : <ChevronDown size={16} className="text-slate-400" />}
          </button>
          {showCompetitors && (
            <table className="w-full text-sm border-t border-slate-100">
              <thead className="bg-slate-50">
                <tr>
                  <th className="text-left px-4 py-2.5 font-medium text-slate-600">Магазин</th>
                  <th className="text-right px-4 py-2.5 font-medium text-slate-600">Ціна</th>
                  <th className="text-center px-4 py-2.5 font-medium text-slate-600 hidden sm:table-cell">Наявність</th>
                  <th className="text-right px-4 py-2.5 font-medium text-slate-600 hidden md:table-cell">Вага</th>
                  <th className="px-4 py-2.5"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {result.competitors.map((c) => (
                  <tr key={c.domain} className="hover:bg-slate-50">
                    <td className="px-4 py-2.5 font-medium text-slate-700">{c.domain}</td>
                    <td className="px-4 py-2.5 text-right font-bold">{c.price.toFixed(0)} {c.currency}</td>
                    <td className="px-4 py-2.5 text-center hidden sm:table-cell text-xs">
                      {c.in_stock === true ? <span className="text-green-600">є</span> : c.in_stock === false ? <span className="text-red-500">нема</span> : "—"}
                    </td>
                    <td className="px-4 py-2.5 text-right hidden md:table-cell text-xs text-slate-500">
                      {c.effective_weight.toFixed(2)}
                    </td>
                    <td className="px-4 py-2.5">
                      <a href={c.url} target="_blank" rel="noopener noreferrer"
                        className="p-1.5 hover:bg-blue-50 rounded text-slate-400 hover:text-blue-600 inline-flex">
                        <ExternalLink size={14} />
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

function AutoLabel({ auto, onToggle }: { auto: boolean; onToggle: () => void }) {
  return (
    <label className="flex items-center gap-1.5 cursor-pointer select-none ml-3">
      <input
        type="checkbox"
        checked={auto}
        onChange={onToggle}
        className="rounded accent-blue-600"
      />
      <span className="flex items-center gap-1 text-xs text-blue-700 font-medium">
        <Database size={11} /> Авто (з БД)
      </span>
    </label>
  );
}

function RecommendationsContent() {
  const searchParams = useSearchParams();
  const [article, setArticle]         = useState(searchParams.get("article") ?? "");
  const [currentPrice, setCurrentPrice] = useState("");
  const [stockLevel, setStockLevel]   = useState(0.5);
  const [demand, setDemand]           = useState(0.5);
  const [autoStock, setAutoStock]     = useState(true);
  const [autoDemand, setAutoDemand]   = useState(true);
  const [running, setRunning]         = useState(false);
  const [status, setStatus]           = useState("");
  const [result, setResult]           = useState<RecommendResult | null>(null);
  const [resultArticle, setResultArticle] = useState("");

  async function startRecommend() {
    if (!article.trim()) return;
    setResult(null);
    setRunning(true);
    setStatus("Скрапінг конкурентів...");
    try {
      const { task_id } = await recommendApi.start(article.trim(), {
        own_stock_level: autoStock  ? undefined : stockLevel,
        demand_velocity: autoDemand ? undefined : demand,
        current_price:   currentPrice ? parseFloat(currentPrice) : undefined,
      });

      const poll = async () => {
        const t = await recommendApi.pollTask(task_id);
        if (t.status === "done") {
          setResult(t.result ?? null);
          setResultArticle(article.trim());
          setStatus("");
          setRunning(false);
        } else if (t.status === "error") {
          setStatus(`Помилка: ${t.error}`);
          setRunning(false);
        } else {
          setStatus(`Статус: ${t.status}...`);
          setTimeout(poll, 3000);
        }
      };
      setTimeout(poll, 3000);
    } catch (e: unknown) {
      setStatus(`Помилка: ${e instanceof Error ? e.message : String(e)}`);
      setRunning(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Рекомендація ціни</h1>
        <p className="text-slate-500 mt-1">Нечітка логіка для оптимальної ціни</p>
      </div>

      {/* Form */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Артикул *</label>
            <input
              value={article}
              onChange={(e) => setArticle(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && startRecommend()}
              placeholder="1K0407151BC"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-green-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Наша поточна ціна (₴)</label>
            <input
              type="number" min="0" step="0.01"
              value={currentPrice}
              onChange={(e) => setCurrentPrice(e.target.value)}
              placeholder="2850"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Stock level */}
          <div>
            <div className="flex items-center mb-2">
              <label className="text-sm font-medium text-slate-700">
                Залишок:&nbsp;
                {autoStock ? (
                  <span className="text-blue-600 font-normal text-xs">визначиться автоматично</span>
                ) : (
                  <span className="font-mono text-green-700">{stockLevel.toFixed(1)}</span>
                )}
                <span className="text-slate-400 font-normal ml-1 text-xs">(0=мало, 1=багато)</span>
              </label>
              <AutoLabel auto={autoStock} onToggle={() => setAutoStock((v) => !v)} />
            </div>
            <input
              type="range" min="0" max="1" step="0.1"
              value={stockLevel}
              onChange={(e) => setStockLevel(parseFloat(e.target.value))}
              disabled={autoStock}
              className={`w-full accent-green-500 ${autoStock ? "opacity-40 cursor-not-allowed" : ""}`}
            />
            <div className="flex justify-between text-xs text-slate-400 mt-0.5">
              <span>Мало</span><span>Багато</span>
            </div>
          </div>

          {/* Demand velocity */}
          <div>
            <div className="flex items-center mb-2">
              <label className="text-sm font-medium text-slate-700">
                Попит:&nbsp;
                {autoDemand ? (
                  <span className="text-blue-600 font-normal text-xs">визначиться автоматично</span>
                ) : (
                  <span className="font-mono text-green-700">{demand.toFixed(1)}</span>
                )}
                <span className="text-slate-400 font-normal ml-1 text-xs">(0=слабкий, 1=сильний)</span>
              </label>
              <AutoLabel auto={autoDemand} onToggle={() => setAutoDemand((v) => !v)} />
            </div>
            <input
              type="range" min="0" max="1" step="0.1"
              value={demand}
              onChange={(e) => setDemand(parseFloat(e.target.value))}
              disabled={autoDemand}
              className={`w-full accent-green-500 ${autoDemand ? "opacity-40 cursor-not-allowed" : ""}`}
            />
            <div className="flex justify-between text-xs text-slate-400 mt-0.5">
              <span>Слабкий</span><span>Сильний</span>
            </div>
          </div>
        </div>

        {(autoStock || autoDemand) && (
          <p className="text-xs text-blue-700 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 flex items-center gap-1.5">
            <Database size={12} />
            Параметри з позначкою "Авто" будуть розраховані на основі реальних даних продажів з БД
          </p>
        )}

        <button
          onClick={startRecommend}
          disabled={running || !article.trim()}
          className="flex items-center gap-2 px-5 py-2.5 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-60 text-sm font-medium transition-colors shadow-sm"
        >
          <TrendingUp size={15} />
          {running ? "Аналіз ринку..." : "Отримати рекомендацію"}
        </button>

        {status && (
          <p className="text-sm text-green-700 bg-green-50 px-3 py-2 rounded-lg">{status}</p>
        )}
      </div>

      {/* Result */}
      {result && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-slate-800">Результат аналізу</h2>
            <Link href={`/products/${resultArticle}`} className="text-sm text-blue-600 hover:underline">
              Деталі товару →
            </Link>
          </div>
          <ResultCard result={result} article={resultArticle} />
        </div>
      )}
    </div>
  );
}

export default function RecommendationsPage() {
  return (
    <Suspense fallback={<p className="text-slate-400 mt-8 text-center">Завантаження...</p>}>
      <RecommendationsContent />
    </Suspense>
  );
}
