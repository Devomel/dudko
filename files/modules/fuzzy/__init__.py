"""
Модуль нечіткої логіки для оновлення власних цін.

Публічний API:
    FuzzyPricingEngine  — двигун рекомендацій
    PriceRecommendation — структура результату
"""

from modules.fuzzy.engine import FuzzyPricingEngine, PriceRecommendation

__all__ = ["FuzzyPricingEngine", "PriceRecommendation"]
