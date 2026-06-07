"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  productsApi, scrapingApi, statsApi,
  type Product, type BatchScrapingTask,
} from "@/lib/api";
import {
  Plus, Search, ChevronRight, Pencil, ToggleLeft, ToggleRight,
  Trash2, AlertTriangle, Activity, X,
} from "lucide-react";

const positionColors: Record<string, string> = {
  lowest:       "bg-green-100 text-green-700",
  competitive:  "bg-blue-100 text-blue-700",
  above_market: "bg-red-100 text-red-700",
};

// ── Product Form Modal ─────────────────────────────────────────────────────────
function ProductModal({
  initial,
  categories,
  brands,
  onSave,
  onClose,
}: {
  initial?: Partial<Product>;
  categories: { slug: string; name: string }[];
  brands: string[];
  onSave: () => void;
  onClose: () => void;
}) {
  const [article, setArticle]       = useState(initial?.article ?? "");
  const [name, setName]             = useState(initial?.name ?? "");
  const [category, setCategory]     = useState(initial?.category ?? "");
  const [brand, setBrand]           = useState(initial?.brand ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [price, setPrice]           = useState(String(initial?.price ?? ""));
  const [quantity, setQuantity]     = useState(String(initial?.quantity ?? 0));
  const [warehouse, setWarehouse]   = useState(initial?.warehouse ?? "");
  const [saving, setSaving]         = useState(false);
  const [error, setError]           = useState<string | null>(null);

  const isEdit = Boolean(initial?.article);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      if (isEdit) {
        await productsApi.update(initial!.article!, { name, description, category, brand });
      } else {
        await productsApi.create({ article, name, category, brand, description });
      }
      if (price || quantity) {
        const art = isEdit ? initial!.article! : article;
        await productsApi.setStock(art, {
          price: price ? parseFloat(price) : undefined,
          quantity: parseInt(quantity) || 0,
          warehouse,
        });
      }
      onSave();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 p-6">
        <h2 className="text-lg font-semibold text-slate-900 mb-5">
          {isEdit ? `Редагування: ${initial!.article}` : "Новий товар"}
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          {!isEdit && (
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Артикул *</label>
              <input
                required value={article} onChange={(e) => setArticle(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="1K0407151BC"
              />
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Назва *</label>
            <input
              required value={name} onChange={(e) => setName(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Шрус зовнішній"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Категорія</label>
              <select value={category} onChange={(e) => setCategory(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white">
                <option value="">— не вказано —</option>
                {categories.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Бренд</label>
              <input value={brand} onChange={(e) => setBrand(e.target.value)}
                list="brands-list"
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="VW, BMW..."
              />
              <datalist id="brands-list">
                {brands.map((b) => <option key={b} value={b} />)}
              </datalist>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Опис</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <hr className="border-slate-200" />
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Ціна (₴)</label>
              <input type="number" min="0" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="2850"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Кількість</label>
              <input type="number" min="0" value={quantity} onChange={(e) => setQuantity(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Склад</label>
              <input value={warehouse} onChange={(e) => setWarehouse(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="Склад А"
              />
            </div>
          </div>

          {error && <p className="text-red-600 text-sm">{error}</p>}

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">
              Скасувати
            </button>
            <button type="submit" disabled={saving}
              className="px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-60 transition-colors">
              {saving ? "Збереження..." : "Зберегти"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Delete Confirmation Modal ──────────────────────────────────────────────────
function DeleteConfirmModal({
  product,
  onConfirm,
  onClose,
}: {
  product: Product;
  onConfirm: () => Promise<void>;
  onClose: () => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    setDeleting(true);
    setError(null);
    try {
      await onConfirm();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setDeleting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
            <AlertTriangle size={20} className="text-red-600" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Видалити товар</h2>
            <p className="text-sm text-slate-500">Цю дію неможливо скасувати</p>
          </div>
        </div>
        <p className="text-sm text-slate-700 mb-4">
          Видалити <span className="font-mono font-semibold">{product.article}</span>{" "}
          — <span className="font-medium">{product.name}</span>?
          Буде видалено також всю історію цін та дані продажів.
        </p>
        {error && <p className="text-red-600 text-sm mb-3">{error}</p>}
        <div className="flex justify-end gap-3">
          <button type="button" onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">
            Скасувати
          </button>
          <button onClick={handleDelete} disabled={deleting}
            className="px-4 py-2 text-sm font-medium bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-60 transition-colors">
            {deleting ? "Видалення..." : "Видалити назавжди"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Batch Scrape Progress ──────────────────────────────────────────────────────
function BatchProgress({ task, onClose }: { task: BatchScrapingTask; onClose: () => void }) {
  const pct = task.total > 0 ? Math.round((task.done / task.total) * 100) : 0;
  const okCount = Object.keys(task.results).length;
  const errCount = Object.keys(task.errors).length;
  const isRunning = task.status === "pending" || task.status === "running";

  return (
    <div className="bg-purple-50 border border-purple-200 rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Activity size={14} className={`text-purple-600 ${isRunning ? "animate-pulse" : ""}`} />
          <span className="text-sm font-medium text-purple-800">
            {isRunning
              ? `Скрапінг… ${task.done}/${task.total}${task.current ? ` — ${task.current}` : ""}`
              : `Готово: ${okCount} OK, ${errCount} помилок`}
          </span>
        </div>
        {!isRunning && (
          <button onClick={onClose} className="text-purple-400 hover:text-purple-700 transition-colors">
            <X size={16} />
          </button>
        )}
      </div>
      <div className="w-full bg-purple-100 rounded-full h-1.5">
        <div
          className="bg-purple-500 h-1.5 rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      {task.status === "done" && errCount > 0 && (
        <p className="text-xs text-red-600 mt-2">
          Помилки: {Object.keys(task.errors).join(", ")}
        </p>
      )}
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────
export default function ProductsPage() {
  const [products, setProducts]       = useState<Product[]>([]);
  const [loading, setLoading]         = useState(true);
  const [q, setQ]                     = useState("");
  const [categories, setCategories]   = useState<{ slug: string; name: string }[]>([]);
  const [brands, setBrands]           = useState<string[]>([]);
  const [filterCat, setFilterCat]     = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [modal, setModal]             = useState<"create" | Product | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Product | null>(null);

  // Batch scraping
  const [selected, setSelected]       = useState<Set<string>>(new Set());
  const [batchTask, setBatchTask]     = useState<BatchScrapingTask | null>(null);
  const [batchRunning, setBatchRunning] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await productsApi.list({
        q: q || undefined,
        category: filterCat || undefined,
        active_only: !showInactive,
      });
      setProducts(data);
    } finally {
      setLoading(false);
    }
  }, [q, filterCat, showInactive]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    statsApi.categories().then(setCategories);
    statsApi.brands().then(setBrands);
  }, []);

  async function toggleActive(p: Product) {
    if (p.is_active) await productsApi.deactivate(p.article);
    else await productsApi.activate(p.article);
    load();
  }

  function toggleSelect(article: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(article) ? next.delete(article) : next.add(article);
      return next;
    });
  }

  const allVisible = products.map((p) => p.article);
  const allChecked = allVisible.length > 0 && allVisible.every((a) => selected.has(a));
  const someChecked = allVisible.some((a) => selected.has(a)) && !allChecked;

  function toggleSelectAll() {
    if (allChecked) {
      setSelected((prev) => {
        const next = new Set(prev);
        allVisible.forEach((a) => next.delete(a));
        return next;
      });
    } else {
      setSelected((prev) => new Set([...prev, ...allVisible]));
    }
  }

  async function startBatchScrape() {
    if (selected.size === 0 || batchRunning) return;
    setBatchTask(null);
    setBatchRunning(true);
    try {
      const { task_id } = await scrapingApi.startBatch(Array.from(selected));
      const poll = async () => {
        const t = await scrapingApi.pollBatchTask(task_id);
        setBatchTask(t);
        if (t.status === "done" || t.status === "error") {
          setBatchRunning(false);
        } else {
          setTimeout(poll, 3000);
        }
      };
      setTimeout(poll, 2000);
    } catch {
      setBatchRunning(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Каталог товарів</h1>
          <p className="text-slate-500 mt-1">{products.length} позицій</p>
        </div>
        <div className="flex items-center gap-2">
          {selected.size > 0 && (
            <button
              onClick={startBatchScrape}
              disabled={batchRunning}
              className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-60 text-sm font-medium transition-colors shadow-sm"
            >
              <Activity size={15} className={batchRunning ? "animate-pulse" : ""} />
              Скрапити вибрані ({selected.size})
            </button>
          )}
          {selected.size > 0 && (
            <button
              onClick={() => setSelected(new Set())}
              className="px-3 py-2 text-sm text-slate-500 hover:bg-slate-100 rounded-lg transition-colors"
            >
              Зняти
            </button>
          )}
          <button
            onClick={() => setModal("create")}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium transition-colors shadow-sm"
          >
            <Plus size={16} /> Додати товар
          </button>
        </div>
      </div>

      {/* Batch progress */}
      {batchTask && (
        <BatchProgress task={batchTask} onClose={() => setBatchTask(null)} />
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-48">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Пошук по артикулу або назві..."
            className="w-full pl-9 pr-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <select value={filterCat} onChange={(e) => setFilterCat(e.target.value)}
          className="border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option value="">Всі категорії</option>
          {categories.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
        </select>
        <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
          <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} className="rounded" />
          Показати неактивні
        </label>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {loading ? (
          <p className="p-8 text-center text-slate-400">Завантаження...</p>
        ) : products.length === 0 ? (
          <p className="p-8 text-center text-slate-400">Товарів не знайдено</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-4 py-3 w-8">
                  <input
                    type="checkbox"
                    checked={allChecked}
                    ref={(el) => { if (el) el.indeterminate = someChecked; }}
                    onChange={toggleSelectAll}
                    className="rounded"
                  />
                </th>
                <th className="text-left px-4 py-3 font-medium text-slate-600">Артикул</th>
                <th className="text-left px-4 py-3 font-medium text-slate-600">Назва</th>
                <th className="text-left px-4 py-3 font-medium text-slate-600 hidden md:table-cell">Категорія</th>
                <th className="text-left px-4 py-3 font-medium text-slate-600 hidden lg:table-cell">Бренд</th>
                <th className="text-right px-4 py-3 font-medium text-slate-600">Ціна</th>
                <th className="text-right px-4 py-3 font-medium text-slate-600 hidden sm:table-cell">К-ть</th>
                <th className="text-center px-4 py-3 font-medium text-slate-600">Дії</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {products.map((p) => {
                const isSelected = selected.has(p.article);
                return (
                  <tr
                    key={p.article}
                    className={`hover:bg-slate-50 transition-colors ${!p.is_active ? "opacity-50" : ""} ${isSelected ? "bg-purple-50 hover:bg-purple-50" : ""}`}
                  >
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelect(p.article)}
                        className="rounded accent-purple-600"
                      />
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-blue-700">
                      <Link href={`/products/${p.article}`} className="hover:underline flex items-center gap-1">
                        {p.article} <ChevronRight size={12} />
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-slate-800 max-w-xs truncate">{p.name}</td>
                    <td className="px-4 py-3 hidden md:table-cell">
                      {p.category && (
                        <span className="px-2 py-0.5 bg-slate-100 text-slate-600 rounded-full text-xs">{p.category}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 hidden lg:table-cell text-slate-600 text-xs">{p.brand}</td>
                    <td className="px-4 py-3 text-right font-medium text-slate-900">
                      {p.price ? `${Number(p.price).toFixed(0)} ₴` : <span className="text-slate-400">—</span>}
                    </td>
                    <td className="px-4 py-3 text-right hidden sm:table-cell">
                      <span className={p.quantity ? "text-green-700 font-medium" : "text-slate-400"}>
                        {p.quantity ?? 0}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-center gap-1">
                        <button onClick={() => setModal(p)} title="Редагувати"
                          className="p-1.5 hover:bg-blue-50 rounded text-slate-400 hover:text-blue-600 transition-colors">
                          <Pencil size={14} />
                        </button>
                        <button onClick={() => toggleActive(p)} title={p.is_active ? "Деактивувати" : "Активувати"}
                          className="p-1.5 hover:bg-slate-100 rounded text-slate-400 hover:text-slate-700 transition-colors">
                          {p.is_active ? <ToggleRight size={14} /> : <ToggleLeft size={14} />}
                        </button>
                        <button onClick={() => setDeleteTarget(p)} title="Видалити назавжди"
                          className="p-1.5 hover:bg-red-50 rounded text-slate-400 hover:text-red-600 transition-colors">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {modal && (
        <ProductModal
          initial={modal === "create" ? undefined : (modal as Product)}
          categories={categories}
          brands={brands}
          onSave={() => { setModal(null); load(); }}
          onClose={() => setModal(null)}
        />
      )}

      {deleteTarget && (
        <DeleteConfirmModal
          product={deleteTarget}
          onConfirm={async () => {
            await productsApi.hardDelete(deleteTarget.article);
            setDeleteTarget(null);
            load();
          }}
          onClose={() => setDeleteTarget(null)}
        />
      )}
    </div>
  );
}
