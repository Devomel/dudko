"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { statsApi, type DashboardStats } from "@/lib/api";
import { Package, Search, TrendingUp, Database, Activity } from "lucide-react";

function StatCard({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: string | number; color: string }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 flex items-center gap-4 shadow-sm">
      <div className={`p-3 rounded-lg ${color}`}>{icon}</div>
      <div>
        <p className="text-sm text-slate-500">{label}</p>
        <p className="text-2xl font-bold text-slate-900">{value}</p>
      </div>
    </div>
  );
}

const positionLabels: Record<string, { label: string; color: string }> = {
  lowest:       { label: "Найнижча",    color: "bg-green-100 text-green-800" },
  competitive:  { label: "Конкурентна", color: "bg-blue-100 text-blue-800" },
  above_market: { label: "Вище ринку",  color: "bg-red-100 text-red-800" },
};

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    statsApi.dashboard()
      .then(setStats)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-slate-400 mt-8 text-center">Завантаження...</p>;
  if (error) return (
    <div className="mt-8 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
      Помилка підключення до API: {error}
    </div>
  );
  if (!stats) return null;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Дашборд</h1>
        <p className="text-slate-500 mt-1">Огляд системи моніторингу цін</p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={<Package size={22} className="text-blue-600" />}
          label="Товарів"
          value={stats.total_products}
          color="bg-blue-50"
        />
        <StatCard
          icon={<Activity size={22} className="text-purple-600" />}
          label="Сесій скрапінгу"
          value={stats.total_sessions}
          color="bg-purple-50"
        />
        <StatCard
          icon={<Database size={22} className="text-orange-600" />}
          label="Джерел"
          value={stats.total_sources}
          color="bg-orange-50"
        />
        <StatCard
          icon={<TrendingUp size={22} className="text-green-600" />}
          label="Сер. ринок (7д)"
          value={stats.avg_market_price_7d ? `${stats.avg_market_price_7d.toFixed(0)} ₴` : "—"}
          color="bg-green-50"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Price positions */}
        {stats.price_positions.length > 0 && (
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
            <h2 className="font-semibold text-slate-800 mb-4">Позиції цін</h2>
            <div className="space-y-3">
              {stats.price_positions.map((p) => {
                const meta = positionLabels[p.price_position] ?? { label: p.price_position, color: "bg-slate-100 text-slate-700" };
                return (
                  <div key={p.price_position} className="flex items-center justify-between">
                    <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${meta.color}`}>
                      {meta.label}
                    </span>
                    <span className="font-bold text-slate-700">{p.count} товарів</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Recent sessions */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <h2 className="font-semibold text-slate-800 mb-4">Останні сесії скрапінгу</h2>
          {stats.recent_sessions.length === 0 ? (
            <p className="text-sm text-slate-400">Ще немає сесій. Запустіть скрапінг.</p>
          ) : (
            <div className="divide-y divide-slate-100">
              {stats.recent_sessions.map((s) => (
                <div key={s.id} className="py-2.5 flex items-center justify-between text-sm">
                  <div>
                    <Link href={`/products/${s.article}`} className="font-medium text-blue-600 hover:underline">
                      {s.article}
                    </Link>
                    <span className="ml-2 text-slate-400 text-xs">
                      {new Date(s.scraped_at).toLocaleString("uk-UA")}
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-slate-600">{s.sources_found} джерел</span>
                    {s.weighted_avg && (
                      <span className="ml-2 text-slate-900 font-medium">
                        {Number(s.weighted_avg).toFixed(0)} ₴
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Link href="/products" className="flex items-center gap-3 p-4 bg-white rounded-xl border border-slate-200 hover:border-blue-300 hover:shadow-md transition-all shadow-sm group">
          <Package size={20} className="text-blue-500 group-hover:text-blue-700" />
          <span className="font-medium text-slate-700">Каталог товарів</span>
        </Link>
        <Link href="/scraping" className="flex items-center gap-3 p-4 bg-white rounded-xl border border-slate-200 hover:border-purple-300 hover:shadow-md transition-all shadow-sm group">
          <Search size={20} className="text-purple-500 group-hover:text-purple-700" />
          <span className="font-medium text-slate-700">Запустити скрапінг</span>
        </Link>
        <Link href="/scraping" className="flex items-center gap-3 p-4 bg-white rounded-xl border border-slate-200 hover:border-green-300 hover:shadow-md transition-all shadow-sm group">
          <TrendingUp size={20} className="text-green-500 group-hover:text-green-700" />
          <span className="font-medium text-slate-700">Рекомендації цін</span>
        </Link>
      </div>
    </div>
  );
}
