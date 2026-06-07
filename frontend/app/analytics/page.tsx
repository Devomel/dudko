"use client";

import { useEffect, useState } from "react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, Legend, Cell,
} from "recharts";
import {
  analyticsApi,
  type MonthlySales, type ProductSales, type SeasonalityRow, type StockStatus,
} from "@/lib/api";
import { TrendingUp, ShoppingCart, Package, AlertCircle } from "lucide-react";

const MONTH_LABELS = ["", "Січ", "Лют", "Бер", "Кві", "Тра", "Чер", "Лип", "Сер", "Вер", "Жов", "Лис", "Гру"];
const CATEGORY_COLORS: Record<string, string> = {
  гальма:     "#ef4444",
  ходова:     "#3b82f6",
  підвіска:   "#8b5cf6",
  трансмісія: "#f59e0b",
  двигун:     "#10b981",
  інше:       "#6b7280",
};

// ── Utils ─────────────────────────────────────────────────────────────────────
function fmt(n: number) {
  return n.toLocaleString("uk-UA", { maximumFractionDigits: 0 });
}

function monthLabel(iso: string) {
  const [, m] = iso.split("-");
  return MONTH_LABELS[parseInt(m)] ?? iso;
}

// ── Seasonality heatmap ───────────────────────────────────────────────────────
function SeasonalityHeatmap({ rows }: { rows: SeasonalityRow[] }) {
  if (rows.length === 0) return null;

  const categories = [...new Set(rows.map((r) => r.category))].sort();
  const grid: Record<string, Record<number, number>> = {};
  for (const r of rows) {
    if (!grid[r.category]) grid[r.category] = {};
    grid[r.category][r.month] = r.total_units;
  }

  const maxVal = Math.max(...rows.map((r) => r.total_units));

  function intensity(val: number) {
    const t = val / maxVal;
    const r = Math.round(239 - t * (239 - 59));
    const g = Math.round(246 - t * (246 - 130));
    const b = Math.round(253 - t * (253 - 246));
    return `rgb(${r},${g},${b})`;
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
      <h2 className="font-semibold text-slate-800 mb-4">Сезонність продажів по категоріях</h2>
      <div className="overflow-x-auto">
        <table className="text-xs w-full">
          <thead>
            <tr>
              <th className="text-left pr-4 py-1 font-medium text-slate-600 min-w-28">Категорія</th>
              {Array.from({ length: 12 }, (_, i) => (
                <th key={i + 1} className="text-center px-2 py-1 font-medium text-slate-600 min-w-10">
                  {MONTH_LABELS[i + 1]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {categories.map((cat) => (
              <tr key={cat}>
                <td className="pr-4 py-1.5">
                  <div className="flex items-center gap-1.5">
                    <span
                      className="w-2.5 h-2.5 rounded-sm flex-shrink-0"
                      style={{ background: CATEGORY_COLORS[cat] ?? "#6b7280" }}
                    />
                    <span className="font-medium text-slate-700 capitalize">{cat}</span>
                  </div>
                </td>
                {Array.from({ length: 12 }, (_, i) => {
                  const val = grid[cat]?.[i + 1] ?? 0;
                  return (
                    <td key={i} className="text-center px-1 py-1">
                      <div
                        title={`${val} шт`}
                        className="w-8 h-8 mx-auto rounded flex items-center justify-center font-medium text-slate-700"
                        style={{ background: val > 0 ? intensity(val) : "#f8fafc" }}
                      >
                        {val || ""}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-400 mt-3">Колір = інтенсивність продажів відносно максимуму</p>
    </div>
  );
}

// ── Stock table ───────────────────────────────────────────────────────────────
function StockTable({ rows }: { rows: StockStatus[] }) {
  function supplyColor(months: number | null) {
    if (months === null) return "text-slate-400";
    if (months < 0.5) return "text-red-600 font-bold";
    if (months < 1.5) return "text-orange-500 font-semibold";
    if (months < 3) return "text-yellow-600";
    return "text-green-600";
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <div className="p-4 border-b border-slate-100 flex items-center gap-2">
        <Package size={16} className="text-slate-500" />
        <h2 className="font-semibold text-slate-800">Залишки на складі</h2>
        <span className="ml-auto text-xs text-slate-400">{rows.length} позицій</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="text-left px-4 py-2.5 font-medium text-slate-600">Артикул</th>
              <th className="text-left px-4 py-2.5 font-medium text-slate-600 hidden md:table-cell">Назва</th>
              <th className="text-left px-4 py-2.5 font-medium text-slate-600 hidden lg:table-cell">Категорія</th>
              <th className="text-right px-4 py-2.5 font-medium text-slate-600">Залишок</th>
              <th className="text-right px-4 py-2.5 font-medium text-slate-600 hidden sm:table-cell">Прогноз/міс</th>
              <th className="text-right px-4 py-2.5 font-medium text-slate-600">Міс. запасу</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r) => (
              <tr key={r.article} className="hover:bg-slate-50">
                <td className="px-4 py-2.5 font-mono text-xs text-blue-700">{r.article}</td>
                <td className="px-4 py-2.5 text-slate-700 hidden md:table-cell max-w-xs truncate">{r.name}</td>
                <td className="px-4 py-2.5 hidden lg:table-cell">
                  {r.category && (
                    <span
                      className="px-2 py-0.5 rounded-full text-xs font-medium text-white"
                      style={{ background: CATEGORY_COLORS[r.category] ?? "#6b7280" }}
                    >
                      {r.category}
                    </span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-right">
                  <span className={r.current_stock <= 3 ? "text-red-600 font-bold" : "text-slate-900 font-medium"}>
                    {r.current_stock}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-right text-slate-600 hidden sm:table-cell">
                  {r.monthly_forecast ? r.monthly_forecast.toFixed(1) : "—"}
                </td>
                <td className={`px-4 py-2.5 text-right ${supplyColor(r.months_of_supply)}`}>
                  {r.months_of_supply !== null ? r.months_of_supply.toFixed(1) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function AnalyticsPage() {
  const [monthly, setMonthly] = useState<MonthlySales[]>([]);
  const [topSellers, setTopSellers] = useState<ProductSales[]>([]);
  const [seasonality, setSeasonality] = useState<SeasonalityRow[]>([]);
  const [stock, setStock] = useState<StockStatus[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      analyticsApi.monthlySales(12),
      analyticsApi.topSellers(15),
      analyticsApi.seasonality(),
      analyticsApi.stock(),
    ])
      .then(([m, t, s, st]) => {
        setMonthly(m);
        setTopSellers(t);
        setSeasonality(s);
        setStock(st);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <p className="text-slate-400 mt-8 text-center">Завантаження аналітики...</p>;
  }

  const totalUnits = monthly.reduce((s, m) => s + m.total_units, 0);
  const totalRevenue = monthly.reduce((s, m) => s + m.total_revenue, 0);
  const bestMonth = monthly.reduce((a, b) => (b.total_units > a.total_units ? b : a), monthly[0]);
  const lowStockCount = stock.filter((s) => s.months_of_supply !== null && s.months_of_supply < 1).length;

  const monthlyChart = monthly.map((m) => ({
    month: monthLabel(m.month),
    units: m.total_units,
    revenue: Math.round(m.total_revenue),
  }));

  const topChart = topSellers.slice(0, 10).map((p) => ({
    name: p.article,
    units: p.total_units,
    color: CATEGORY_COLORS[p.category ?? "інше"] ?? "#6b7280",
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Аналітика продажів</h1>
        <p className="text-slate-500 mt-1">Часові ряди, сезонність та залишки — за останній рік</p>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { icon: ShoppingCart, label: "Продано за рік", value: `${fmt(totalUnits)} шт`, color: "text-blue-600" },
          { icon: TrendingUp, label: "Виручка за рік", value: `${fmt(totalRevenue)} ₴`, color: "text-green-600" },
          { icon: TrendingUp, label: "Кращий місяць", value: bestMonth ? `${monthLabel(bestMonth.month)} (${fmt(bestMonth.total_units)})` : "—", color: "text-purple-600" },
          { icon: AlertCircle, label: "Мало запасу", value: `${lowStockCount} позицій`, color: lowStockCount > 0 ? "text-red-600" : "text-slate-400" },
        ].map((k) => (
          <div key={k.label} className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
            <div className="flex items-center gap-2 mb-1">
              <k.icon size={16} className={k.color} />
              <p className="text-xs text-slate-500">{k.label}</p>
            </div>
            <p className={`text-lg font-bold ${k.color}`}>{k.value}</p>
          </div>
        ))}
      </div>

      {/* Monthly sales chart */}
      {monthlyChart.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
          <h2 className="font-semibold text-slate-800 mb-4">Продажі по місяцях</h2>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={monthlyChart} margin={{ top: 4, right: 24, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="month" tick={{ fontSize: 12 }} />
              <YAxis yAxisId="left" tick={{ fontSize: 11 }} unit=" шт" width={58} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} unit=" ₴" width={80} />
              <Tooltip
                formatter={(val, name) =>
                  name === "units"
                    ? [`${fmt(Number(val))} шт`, "Кількість"]
                    : [`${fmt(Number(val))} ₴`, "Виручка"]
                }
              />
              <Legend formatter={(v) => (v === "units" ? "Кількість" : "Виручка")} />
              <Line yAxisId="left" type="monotone" dataKey="units" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} />
              <Line yAxisId="right" type="monotone" dataKey="revenue" stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} strokeDasharray="5 5" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Top sellers */}
      {topChart.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
          <h2 className="font-semibold text-slate-800 mb-4">Топ-10 продавців</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={topChart} margin={{ top: 4, right: 12, left: 0, bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="name" angle={-35} textAnchor="end" tick={{ fontSize: 10 }} interval={0} />
              <YAxis tick={{ fontSize: 11 }} unit=" шт" width={55} />
              <Tooltip formatter={(v) => [`${fmt(Number(v))} шт`, "Продано"]} />
              <Bar dataKey="units" radius={[4, 4, 0, 0]}>
                {topChart.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>

          {/* Legend by category */}
          <div className="flex flex-wrap gap-3 mt-3">
            {Object.entries(CATEGORY_COLORS).map(([cat, color]) => (
              <span key={cat} className="flex items-center gap-1.5 text-xs text-slate-600">
                <span className="w-3 h-3 rounded-sm" style={{ background: color }} />
                {cat}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Seasonality heatmap */}
      <SeasonalityHeatmap rows={seasonality} />

      {/* Stock table */}
      <StockTable rows={stock} />
    </div>
  );
}
