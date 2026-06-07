"""
Модуль нечіткої логіки для рекомендації власної ціни.

Архітектура: два послідовних Mamdani FIS

──────────────────────────────────────────────────────
Блок 1 — Ринкові умови (market FIS)
    Входи:
        stock_availability  — частка конкурентів де товар є в наявності [0..1]
        market_spread       — відносний розкид цін (max-min)/median [0..∞]
    Вихід:
        market_position [0..1]   базова позиція ціни між floor і ceiling

Правила (9 IF-THEN):
    abundant + tight     → low
    abundant + moderate  → medium_low
    abundant + volatile  → medium_low
    normal   + tight     → medium_low
    normal   + moderate  → medium
    normal   + volatile  → medium
    scarce   + tight     → medium
    scarce   + moderate  → medium_high
    scarce   + volatile  → high

──────────────────────────────────────────────────────
Блок 2 — Власні умови (own FIS)       [опціональний]
    Входи:
        own_stock_level  — рівень власних залишків [0=мало, 1=багато]
        demand_velocity  — швидкість продажів [0=не продається, 1=ходовий]
    Вихід:
        own_adjustment ∈ [-0.30, +0.30]  корекція market_position

Правила (9 IF-THEN):
    surplus + fast   → strong_premium  (+0.24) — ходова + багато = не продаємо дешево
    surplus + normal → neutral         ( 0.00) — нейтрально
    surplus + slow   → discount        (-0.12) — стоїть → знижуємо
    medium  + fast   → premium         (+0.12) — попит є → підвищуємо
    medium  + normal → neutral         ( 0.00)
    medium  + slow   → discount        (-0.12)
    low     + fast   → neutral         ( 0.00) — залишки, але ходова — тримаємо
    low     + normal → discount        (-0.12) — залишки → звільняємо склад
    low     + slow   → strong_discount (-0.24) — залишки + не продається → знижуємо сильно

──────────────────────────────────────────────────────
Фінальна позиція = clamp(market_position + own_adjustment, 0, 1)

Відображення позиції у ціну:
    floor   = market_min * 1.03   (не нижче мінімуму + 3%)
    ceiling = market_median * 1.20
    recommended = floor + position * (ceiling - floor)
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Optional

from schema import ScrapingBundle, SourceRecord


# ─────────────────────────────────────────────────────────────────────────────
# Структура результату
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PriceRecommendation:
    """Результат роботи модуля нечіткої логіки."""
    article: str
    recommended_price: Optional[float]   # рекомендована ціна, UAH
    confidence: float                    # 0..1: впевненість у рекомендації
    strategy: str                        # 'undercut' | 'competitive' | 'moderate_premium' | 'premium' | 'no_data'
    reasoning: str                       # пояснення людською мовою
    market_min: Optional[float]
    market_median: Optional[float]
    market_max: Optional[float]
    market_wap: Optional[float]          # зважена середня ринкова ціна
    in_stock_ratio: float                # частка конкурентів з наявністю
    source_count: int                    # кількість валідних джерел
    fuzzy_position: float                # фінальна нечітка позиція [0..1] для діагностики
    market_position: float               # ринкова позиція до корекції
    own_stock_level: float               # вхідний параметр власних залишків (0=мало, 1=багато)
    demand_velocity: float               # вхідний параметр попиту (0=слабкий, 1=ходовий)
    own_adjustment: float                # корекція позиції від власних умов [-0.30..+0.30]

    def to_dict(self) -> dict:
        return {
            "article":           self.article,
            "recommended_price": self.recommended_price,
            "confidence":        self.confidence,
            "strategy":          self.strategy,
            "reasoning":         self.reasoning,
            "market": {
                "min":    self.market_min,
                "median": self.market_median,
                "max":    self.market_max,
                "wap":    self.market_wap,
            },
            "in_stock_ratio":    self.in_stock_ratio,
            "source_count":      self.source_count,
            "fuzzy": {
                "market_position": self.market_position,
                "own_adjustment":  self.own_adjustment,
                "final_position":  self.fuzzy_position,
            },
            "own_conditions": {
                "stock_level":     self.own_stock_level,
                "demand_velocity": self.demand_velocity,
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# Функції належності (membership functions)
# ─────────────────────────────────────────────────────────────────────────────

def _trapezoid(x: float, a: float, b: float, c: float, d: float) -> float:
    """
    Трапецієподібна функція належності.
    Повна належність на [b, c], лінійний підйом на [a, b], спад на [c, d].
    """
    if x <= a or x >= d:
        return 0.0
    if b <= x <= c:
        return 1.0
    if x < b:
        return (x - a) / (b - a)
    return (d - x) / (d - c)


def _triangle(x: float, a: float, b: float, c: float) -> float:
    """Трикутна функція належності: _trapezoid з b == c."""
    return _trapezoid(x, a, b, b, c)


# ─────────────────────────────────────────────────────────────────────────────
# Головний клас
# ─────────────────────────────────────────────────────────────────────────────

class FuzzyPricingEngine:
    """
    Двигун нечіткої логіки для встановлення власних цін.

    Вхід:  ScrapingBundle  (контракт від модуля скрапінгу)
           own_stock_level — рівень власних залишків [0..1]  (опціонально)
           demand_velocity — швидкість продажів [0..1]       (опціонально)
    Вихід: PriceRecommendation

    Параметри:
        floor_ratio   — мінімальна надбавка до market_min (default: 1.03 → +3%)
        ceiling_ratio — максимальна надбавка до market_median (default: 1.20 → +20%)
        cog_steps     — дискретизація для CoG-дефазифікації (default: 200)
    """

    def __init__(
        self,
        floor_ratio:   float = 1.03,
        ceiling_ratio: float = 1.20,
        cog_steps:     int   = 200,
    ):
        self.floor_ratio   = floor_ratio
        self.ceiling_ratio = ceiling_ratio
        self.cog_steps     = cog_steps

    # ─────────────────────────── PUBLIC API ──────────────────────────────────

    def recommend(
        self,
        bundle: ScrapingBundle,
        own_stock_level: float = 0.5,
        demand_velocity: float = 0.5,
    ) -> PriceRecommendation:
        """
        Формує рекомендацію щодо власної ціни.

        Args:
            bundle:          результат скрапінгу
            own_stock_level: рівень власних залишків 0..1
                             0.0 = залишки (треба звільняти склад)
                             0.5 = нормальний рівень
                             1.0 = великий запас (ходова позиція)
            demand_velocity: швидкість продажів за останній тиждень/місяць 0..1
                             0.0 = не продається
                             0.5 = нормальний попит
                             1.0 = ходовий товар, продається швидко
        """
        sources = bundle.valid_sources

        if not sources:
            return self._no_data(bundle.article, own_stock_level, demand_velocity)


        # ── 1. Ринкова статистика ────────────────────────────────────────────
        prices      = [s.price for s in sources]
        market_min  = min(prices)
        market_max  = max(prices)
        market_med  = statistics.median(prices)
        market_wap  = bundle.weighted_avg_price

        in_stock_count = sum(1 for s in sources if s.in_stock is True)
        in_stock_ratio = in_stock_count / len(sources)

        spread = (market_max - market_min) / market_med if market_med > 0 else 0.0

        # ── 2. Ринкова фазифікація ───────────────────────────────────────────
        stock_m  = self._fuzzify_stock_availability(in_stock_ratio)
        spread_m = self._fuzzify_market_spread(spread)

        # ── 3. Ринкові правила ───────────────────────────────────────────────
        market_out = self._apply_market_rules(stock_m, spread_m)

        # ── 4. Ринкова дефазифікація → market_position ∈ [0, 1] ─────────────
        market_position = self._defuzzify(market_out)

        # ── 5. Власні умови (склад + попит) ──────────────────────────────────
        own_adjustment = self._calc_own_adjustment(own_stock_level, demand_velocity)

        # Фінальна позиція з корекцією
        position = max(0.0, min(1.0, market_position + own_adjustment))

        # ── 6. Розрахунок рекомендованої ціни ───────────────────────────────
        floor   = market_min * self.floor_ratio
        ceiling = market_med * self.ceiling_ratio
        floor   = min(floor, market_med * 0.85)
        recommended = round(floor + position * (ceiling - floor), 2)

        # ── 7. Впевненість ───────────────────────────────────────────────────
        confidence = self._calc_confidence(sources, spread)

        # ── 8. Стратегія та пояснення ────────────────────────────────────────
        strategy  = self._strategy_name(position)
        reasoning = self._explain(
            position, market_position, own_adjustment,
            stock_m, spread_m, market_out,
            market_min, market_med, market_max, market_wap,
            recommended, in_stock_ratio, len(sources),
            own_stock_level, demand_velocity,
        )

        return PriceRecommendation(
            article           = bundle.article,
            recommended_price = recommended,
            confidence        = confidence,
            strategy          = strategy,
            reasoning         = reasoning,
            market_min        = market_min,
            market_median     = market_med,
            market_max        = market_max,
            market_wap        = market_wap,
            in_stock_ratio    = round(in_stock_ratio, 3),
            source_count      = len(sources),
            fuzzy_position    = round(position, 4),
            market_position   = round(market_position, 4),
            own_stock_level   = own_stock_level,
            demand_velocity   = demand_velocity,
            own_adjustment    = round(own_adjustment, 4),
        )

    # ─────────────────── БЛОК 1: РИНКОВІ УМОВИ ───────────────────────────────

    def _fuzzify_stock_availability(self, ratio: float) -> dict[str, float]:
        """
        Фазифікація наявності товару у конкурентів.

        scarce   [0.0 – 0.40]: менше 40% конкурентів мають товар
        normal   [0.30 – 0.75]: помірна наявність
        abundant [0.60 – 1.0 ]: товар є скрізь
        """
        return {
            "scarce":   _trapezoid(ratio, 0.0,  0.0,  0.20, 0.42),
            "normal":   _triangle (ratio, 0.30, 0.55, 0.80),
            "abundant": _trapezoid(ratio, 0.60, 0.82, 1.0,  1.0 ),
        }

    def _fuzzify_market_spread(self, spread: float) -> dict[str, float]:
        """
        Фазифікація відносного розкиду цін: spread = (max-min)/median.
        Нормалізуємо до [0..1] кепом 3.0.

        tight    [0.0 – 0.30]: ціни згруповані
        moderate [0.15 – 0.65]: помірний розкид
        volatile [0.50 – 1.0 ]: великий розкид
        """
        s = min(spread / 3.0, 1.0)
        return {
            "tight":    _trapezoid(s, 0.0,  0.0,  0.12, 0.28),
            "moderate": _triangle (s, 0.18, 0.40, 0.62),
            "volatile": _trapezoid(s, 0.52, 0.72, 1.0,  1.0 ),
        }

    def _apply_market_rules(
        self,
        stock:  dict[str, float],
        spread: dict[str, float],
    ) -> dict[str, float]:
        """База ринкових правил (Mamdani, AND=min, агрегація=max)."""
        r = stock
        s = spread
        return {
            "low": max([
                min(r["abundant"], s["tight"]),
            ]),
            "medium_low": max([
                min(r["abundant"], s["moderate"]),
                min(r["abundant"], s["volatile"]),
                min(r["normal"],   s["tight"]),
            ]),
            "medium": max([
                min(r["normal"],   s["moderate"]),
                min(r["normal"],   s["volatile"]),
                min(r["scarce"],   s["tight"]),
            ]),
            "medium_high": max([
                min(r["scarce"],   s["moderate"]),
            ]),
            "high": max([
                min(r["scarce"],   s["volatile"]),
            ]),
        }

    def _defuzzify(self, output_sets: dict[str, float]) -> float:
        """
        CoG по дискретному universe [0, 1].
        Центри вихідних множин: 0.10 / 0.30 / 0.50 / 0.70 / 0.90.
        """
        centers = {
            "low":         0.10,
            "medium_low":  0.30,
            "medium":      0.50,
            "medium_high": 0.70,
            "high":        0.90,
        }
        return self._cog(output_sets, centers, x_min=0.0, x_max=1.0)

    # ─────────────────── БЛОК 2: ВЛАСНІ УМОВИ ────────────────────────────────

    def _fuzzify_own_stock(self, level: float) -> dict[str, float]:
        """
        Фазифікація власних залишків на складі.
        level: 0 = залишки (треба звільнити), 1 = великий запас

        low     [0.0 – 0.35]: залишки
        medium  [0.25 – 0.75]: нормальний рівень
        surplus [0.65 – 1.0 ]: великий запас
        """
        return {
            "low":     _trapezoid(level, 0.0,  0.0,  0.15, 0.35),
            "medium":  _triangle (level, 0.25, 0.50, 0.75),
            "surplus": _trapezoid(level, 0.65, 0.85, 1.0,  1.0 ),
        }

    def _fuzzify_demand_velocity(self, velocity: float) -> dict[str, float]:
        """
        Фазифікація швидкості продажів.
        velocity: 0 = не продається, 1 = ходовий товар

        slow   [0.0 – 0.40]: слабкий попит
        normal [0.30 – 0.70]: нормальний попит
        fast   [0.60 – 1.0 ]: ходовий товар
        """
        return {
            "slow":   _trapezoid(velocity, 0.0,  0.0,  0.20, 0.40),
            "normal": _triangle (velocity, 0.30, 0.50, 0.70),
            "fast":   _trapezoid(velocity, 0.60, 0.80, 1.0,  1.0 ),
        }

    def _apply_own_rules(
        self,
        stock:  dict[str, float],
        demand: dict[str, float],
    ) -> dict[str, float]:
        """
        9 правил для власних умов склад × попит → корекція позиції.

        Вихідні множини (universe [0,1] → відображається у [-0.30, +0.30]):
            strong_discount → 0.10 → -0.24
            discount        → 0.30 → -0.12
            neutral         → 0.50 →  0.00
            premium         → 0.70 → +0.12
            strong_premium  → 0.90 → +0.24
        """
        s = stock
        d = demand
        return {
            "strong_discount": max([
                min(s["low"],     d["slow"]),     # залишки + не продається → знижуємо сильно
            ]),
            "discount": max([
                min(s["low"],     d["normal"]),   # залишки + норм попит → звільняємо склад
                min(s["medium"],  d["slow"]),     # норм запас + слабкий → трохи знижуємо
                min(s["surplus"], d["slow"]),     # багато + не продається → знижуємо
            ]),
            "neutral": max([
                min(s["low"],     d["fast"]),     # залишки, але ходова — тримаємо ціну
                min(s["medium"],  d["normal"]),   # норм запас + норм попит
                min(s["surplus"], d["normal"]),   # багато + норм попит
            ]),
            "premium": max([
                min(s["medium"],  d["fast"]),     # норм запас + ходова → підвищуємо
            ]),
            "strong_premium": max([
                min(s["surplus"], d["fast"]),     # багато + ходова → не продаємо дешево!
            ]),
        }

    def _defuzzify_adjustment(self, output_sets: dict[str, float]) -> float:
        """
        CoG по universe [0,1], потім відображення у [-0.30, +0.30].
        cog=0.5 → adjustment=0.0 (нейтральна корекція).
        """
        centers = {
            "strong_discount": 0.10,
            "discount":        0.30,
            "neutral":         0.50,
            "premium":         0.70,
            "strong_premium":  0.90,
        }
        cog = self._cog(output_sets, centers, x_min=0.0, x_max=1.0)
        return (cog - 0.5) * 0.60   # [0,1] → [-0.30, +0.30]

    def _calc_own_adjustment(self, own_stock_level: float, demand_velocity: float) -> float:
        """Розраховує корекцію позиції від власних умов (повноцінний Mamdani)."""
        stock_m  = self._fuzzify_own_stock(own_stock_level)
        demand_m = self._fuzzify_demand_velocity(demand_velocity)
        own_out  = self._apply_own_rules(stock_m, demand_m)
        return self._defuzzify_adjustment(own_out)

    # ─────────────────── СПІЛЬНИЙ CoG ────────────────────────────────────────

    def _cog(
        self,
        output_sets: dict[str, float],
        centers:     dict[str, float],
        x_min:       float = 0.0,
        x_max:       float = 1.0,
        width:       float = 0.20,
    ) -> float:
        """Center of Gravity по дискретному рівномірному universe [x_min, x_max]."""
        step = (x_max - x_min) / self.cog_steps
        numerator = denominator = 0.0
        for i in range(self.cog_steps + 1):
            x  = x_min + i * step
            mu = 0.0
            for name, activation in output_sets.items():
                if activation <= 0:
                    continue
                c   = centers[name]
                raw = max(0.0, 1.0 - abs(x - c) / width)
                mu  = max(mu, min(activation, raw))
            numerator   += x * mu
            denominator += mu
        return (numerator / denominator) if denominator > 0 else (x_min + x_max) / 2.0

    # ─────────────────── HELPERS ─────────────────────────────────────────────

    def _calc_confidence(self, sources: list[SourceRecord], spread: float) -> float:
        n_factor       = min(len(sources) / 6.0, 1.0)
        avg_eff_w      = sum(s.effective_weight for s in sources) / len(sources)
        spread_penalty = max(0.0, 1.0 - spread / 4.0)
        return round(n_factor * avg_eff_w * spread_penalty, 3)

    def _strategy_name(self, position: float) -> str:
        if position < 0.25:
            return "undercut"
        if position < 0.55:
            return "competitive"
        if position < 0.75:
            return "moderate_premium"
        return "premium"

    def _explain(
        self,
        position:        float,
        market_position: float,
        own_adjustment:  float,
        stock_m:         dict,
        spread_m:        dict,
        output_sets:     dict,
        market_min:      float,
        market_med:      float,
        market_max:      float,
        market_wap:      Optional[float],
        recommended:     float,
        in_stock_ratio:  float,
        n_sources:       int,
        own_stock_level: Optional[float],
        demand_velocity: Optional[float],
    ) -> str:
        lines = []

        lines.append(
            f"Ринок: {n_sources} джерел, ціни {market_min:.0f}–{market_max:.0f} UAH "
            f"(медіана {market_med:.0f}, WAP {market_wap:.0f})."
        )

        pct = round(in_stock_ratio * 100)
        dominant_stock = max(stock_m, key=stock_m.get)
        stock_labels   = {"scarce": "дефіцитний", "normal": "нормальний", "abundant": "надлишковий"}
        lines.append(
            f"Конкуренти: {pct}% мають товар → попит {stock_labels[dominant_stock]} "
            f"(scarce={stock_m['scarce']:.2f}, normal={stock_m['normal']:.2f}, abundant={stock_m['abundant']:.2f})."
        )

        dominant_spread = max(spread_m, key=spread_m.get)
        spread_labels   = {"tight": "стабільний", "moderate": "помірний", "volatile": "волатильний"}
        spread_val      = (market_max - market_min) / market_med if market_med else 0
        lines.append(
            f"Розкид цін: {spread_val:.1f}× → ринок {spread_labels[dominant_spread]} "
            f"(tight={spread_m['tight']:.2f}, moderate={spread_m['moderate']:.2f}, volatile={spread_m['volatile']:.2f})."
        )

        active = {k: v for k, v in output_sets.items() if v > 0.05}
        if active:
            rules_str = ", ".join(f"{k}={v:.2f}" for k, v in sorted(active.items(), key=lambda x: -x[1]))
            lines.append(f"Ринкова позиція: {market_position:.3f} (активовано: {rules_str}).")

        if own_stock_level is not None or demand_velocity is not None:
            own_parts = []
            if own_stock_level is not None:
                own_parts.append(f"залишки={own_stock_level:.2f}")
            if demand_velocity is not None:
                own_parts.append(f"попит={demand_velocity:.2f}")
            sign = "+" if own_adjustment >= 0 else ""
            lines.append(
                f"Власні умови ({', '.join(own_parts)}): корекція {sign}{own_adjustment:.3f} → "
                f"фінальна позиція {position:.3f}."
            )

        strategy_ua = {
            "undercut":         "агресивна (нижче ринку)",
            "competitive":      "конкурентна (близько до WAP)",
            "moderate_premium": "помірна надбавка",
            "premium":          "преміум (дефіцит або ходовий товар)",
        }[self._strategy_name(position)]
        lines.append(f"Стратегія: {strategy_ua}. Рекомендована ціна: {recommended:.2f} UAH.")

        return " ".join(lines)

    def _no_data(
        self,
        article:         str,
        own_stock_level: float,
        demand_velocity: float,
    ) -> PriceRecommendation:
        return PriceRecommendation(
            article           = article,
            recommended_price = None,
            confidence        = 0.0,
            strategy          = "no_data",
            reasoning         = "Недостатньо даних для рекомендації (немає валідних цін).",
            market_min        = None,
            market_median     = None,
            market_max        = None,
            market_wap        = None,
            in_stock_ratio    = 0.0,
            source_count      = 0,
            fuzzy_position    = 0.0,
            market_position   = 0.0,
            own_stock_level   = own_stock_level,
            demand_velocity   = demand_velocity,
            own_adjustment    = 0.0,
        )
