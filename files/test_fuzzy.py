from schema import ScrapingBundle, SourceRecord
from modules.fuzzy import FuzzyPricingEngine

bundle = ScrapingBundle(article='1K0407151BC', sources=[
    SourceRecord('rozetka.ua', 'https://rozetka.ua', 1850.0, 'UAH', True,  0.95, 0.9, 'json-ld'),
    SourceRecord('autodoc.ua', 'https://autodoc.ua', 1920.0, 'UAH', True,  0.85, 0.8, 'microdata'),
    SourceRecord('parts.ua',   'https://parts.ua',   2300.0, 'UAH', False, 0.65, 0.6, 'css'),
    SourceRecord('exist.ua',   'https://exist.ua',   2100.0, 'UAH', True,  0.75, 0.7, 'css'),
])

e = FuzzyPricingEngine()

cases = [
    ('Залишки + немає попиту',  0.05, 0.1),
    ('Залишки + є попит',       0.05, 0.9),
    ('Нормально + нормально',   0.50, 0.5),
    ('Багато + ходовий товар',  0.95, 0.9),
    ('Багато + не продається',  0.95, 0.1),
]

print(f"{'Сценарій':<30} {'Ціна':>8}  {'Стратегія':<20} {'Ринок':>7} {'Кориг':>7} {'Фінал':>7}")
print('-' * 82)
for label, stock, demand in cases:
    r = e.recommend(bundle, own_stock_level=stock, demand_velocity=demand)
    print(f"{label:<30} {r.recommended_price:>8.2f}  {r.strategy:<20} {r.market_position:>7.3f} {r.own_adjustment:>+7.3f} {r.fuzzy_position:>7.3f}")
