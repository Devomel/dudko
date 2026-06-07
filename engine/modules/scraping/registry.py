"""
Реєстр надійності джерел.

Вага домену — Байєсівська оцінка за формулою Beta-Binomial:
    weight = (hits + α) / (appearances + α + β)
    α = 0.1, β = 0.9

Нові домени (0/0)  → weight ≈ 0.10  (дуже мала)
Надійний (38/45)   → weight ≈ 0.83
Ідеальний (10/10)  → weight ≈ 0.92

Дані зберігаються у data/source_registry.json всередині проєкту.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from modules.scraping.search import normalize_domain


log = logging.getLogger("scraper.registry")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY_PATH = _PROJECT_ROOT / "data" / "source_registry.json"

_ALPHA = 0.1
_BETA  = 0.9


class SourceRegistry:
    """Реєстр надійності доменів для зважування результатів скрапінгу."""

    def __init__(self, path: Path = REGISTRY_PATH):
        self._path = path
        self._data: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------ I/O --

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception as e:
                log.warning(f"Не вдалося завантажити реєстр: {e}")

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        log.debug(f"Реєстр збережено: {self._path}")

    # ------------------------------------------------------------ recording --

    def _entry(self, domain: str) -> dict:
        if domain not in self._data:
            self._data[domain] = {"appearances": 0, "hits": 0, "last_seen": None}
        return self._data[domain]

    def record_appearance(self, domain: str) -> None:
        """Домен знайдено в результатах пошуку для чергового артикулу."""
        rec = self._entry(domain)
        rec["appearances"] += 1
        rec["last_seen"] = date.today().isoformat()

    def record_success(self, domain: str) -> None:
        """Домен повернув валідну ціну."""
        self._entry(domain)["hits"] += 1

    # -------------------------------------------------------------- weights --

    def get_weight(self, domain: str) -> float:
        rec = self._data.get(domain)
        if rec is None:
            return round(_ALPHA / (_ALPHA + _BETA), 4)
        return round(
            (rec.get("hits", 0) + _ALPHA) /
            (rec.get("appearances", 0) + _ALPHA + _BETA),
            4,
        )

    def sort_urls_by_weight(self, urls: list[str]) -> list[str]:
        """Сортує URL: домени з вищою вагою йдуть першими."""
        return sorted(
            urls,
            key=lambda u: self.get_weight(normalize_domain(u)),
            reverse=True,
        )

    # -------------------------------------------------------------- inspect --

    def all_stats(self) -> list[dict]:
        return [
            {
                "domain": d,
                "appearances": v.get("appearances", 0),
                "hits": v.get("hits", 0),
                "weight": self.get_weight(d),
                "last_seen": v.get("last_seen"),
            }
            for d, v in sorted(
                self._data.items(),
                key=lambda kv: self.get_weight(kv[0]),
                reverse=True,
            )
        ]
