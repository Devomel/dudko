"""Допоміжні функції: нормалізація цін, валют, тексту."""

from __future__ import annotations

import re
from typing import Optional


CURRENCY_MAP = {
    "грн": "UAH", "грн.": "UAH", "uah": "UAH", "₴": "UAH",
    "$": "USD", "usd": "USD",
    "€": "EUR", "eur": "EUR",
    "руб": "RUB", "₽": "RUB",
}


def clean_text(text: Optional[str]) -> str:
    """Прибирає зайві пробіли, переноси, нерозривні пробіли."""
    if not text:
        return ""
    text = text.replace("\xa0", " ").replace("\u202f", " ")
    return re.sub(r"\s+", " ", text).strip()


def normalize_price(raw: Optional[str]) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """
    Приймає рядок типу '1 234,56 грн' і повертає (значення, валюта, raw_cleaned).
    Підтримує українські, європейські та англійські формати чисел.
    """
    if not raw:
        return None, None, None

    raw_clean = clean_text(raw)
    if not raw_clean:
        return None, None, None

    # Валюта
    currency = None
    lowered = raw_clean.lower()
    for token, code in CURRENCY_MAP.items():
        if token in lowered:
            currency = code
            break

    # Шукаємо число повністю — з усіма можливими роздільниками всередині
    pattern = re.compile(r"\d[\d\s\u00a0.,]*\d|\d")
    matches = pattern.findall(raw_clean)
    if not matches:
        return None, currency, raw_clean

    first = matches[0].strip()
    first = re.sub(r"[\s\u00a0]", "", first)  # прибрали пробіли

    if "," in first and "." in first:
        if first.rfind(",") > first.rfind("."):
            # європейський формат: 1.500,00 → 1500.00
            first = first.replace(".", "").replace(",", ".")
        else:
            # англійський формат: 1,234.56 → 1234.56
            first = first.replace(",", "")
    elif "," in first:
        parts = first.split(",")
        if len(parts) == 2 and 1 <= len(parts[1]) <= 2:
            first = first.replace(",", ".")
        else:
            first = first.replace(",", "")
    elif "." in first:
        parts = first.split(".")
        # 1.500 — це 1500 (роздільник тисяч), а не 1.5
        if len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3:
            first = first.replace(".", "")

    try:
        value = float(first)
    except ValueError:
        return None, currency, raw_clean

    if currency is None:
        currency = "UAH"  # за замовчуванням для українських магазинів

    return value, currency, raw_clean
