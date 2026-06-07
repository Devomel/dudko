"""
Базова модель результату та GenericParser.

GenericParser витягує ціну та наявність з чотирьох джерел по черзі:
  1. JSON-LD (Schema.org/Product)  — confidence 0.95
  2. Microdata (itemprop)           — confidence 0.85
  3. OpenGraph (og:price)           — confidence 0.75
  4. CSS-селектори (з фільтром старих цін) — confidence 0.50
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

from bs4 import BeautifulSoup, Tag

from utils import clean_text, normalize_price


log = logging.getLogger("scraper.parser")


# ---------------------------------------------------------------------------
# Впевненість за методом витягу ціни
# ---------------------------------------------------------------------------
PARSER_CONFIDENCE: dict[str, float] = {
    "json-ld":          0.95,
    "microdata":        0.85,
    "ai":               0.82,
    "opengraph":        0.75,
    "search-card":      0.65,
    "prom-min-price":   0.60,
    "css":              0.35,
    "unknown":          0.25,
}

# ---------------------------------------------------------------------------
# Секції-шуми, які видаляємо перед CSS-пошуком ціни
# (каруселі схожих товарів, бічна панель, футер тощо)
# ---------------------------------------------------------------------------
_NOISE_SELECTORS = [
    # Схожі / рекомендовані / перехресні продажі
    "[class*='related']", "[class*='similar']", "[class*='recommended']",
    "[class*='upsell']",  "[class*='cross-sell']", "[class*='also-bought']",
    "[class*='suggestion']", "[class*='viewed']",
    # Слайдери та каруселі
    "[class*='slider']", "[class*='carousel']", "[class*='swiper']",
    # Бічна панель, хедер, футер
    "aside", "footer", "header", "nav",
    "[class*='sidebar']", "[class*='widget']",
    # Загальні шаблонні назви
    ".products-widget", ".catalog-carousel", ".rec-block",
]

# ---------------------------------------------------------------------------
# Якоря кнопки "купити / в кошик"
# ---------------------------------------------------------------------------
_BUY_ANCHOR_SELECTORS = [
    "[class*='add-to-cart']",   "[class*='buy-btn']",    "[class*='buy-button']",
    "[class*='cart-btn']",      "[class*='order-btn']",  "[class*='btn-buy']",
    "[class*='btn-cart']",      "[class*='btn-order']",
    "[data-action='add-to-cart']", "[data-type='buy']",
    "button[class*='buy']",     "button[class*='cart']",
    "button[class*='order']",   "button[class*='купит']",
    "button[class*='кошик']",   "button[class*='замов']",
    "a[class*='buy']",          "a[class*='cart']",
    ".btn-cart", ".btn-buy",
]

_BUY_BUTTON_TEXTS = frozenset({
    "купити", "купить", "buy", "add to cart",
    "замовити", "замовить", "в корзину", "в кошик",
    "додати в кошик", "add to bag", "купити зараз",
    "order now", "buy now",
})

# Кількість рівнів вгору по DOM при пошуку контейнера з ціною
_BUY_CONTEXT_DEPTH = 6

# ---------------------------------------------------------------------------
# Фільтри "старої ціни" (закреслена, до знижки)
# ---------------------------------------------------------------------------
_OLD_PRICE_TAGS = frozenset({"s", "del", "strike"})
_OLD_PRICE_CLASSES = frozenset({
    "old-price", "price-old", "price--old", "price_old",
    "was-price", "price-before", "price-was", "crossed",
    "prev-price", "original-price", "regular-price", "price-strike",
})

# ---------------------------------------------------------------------------
# Детектори наявності товару
# ---------------------------------------------------------------------------
_STOCK_IN_SELECTORS = [
    ".in-stock", "[class*='in-stock']", "[class*='instock']",
    "[data-availability='available']", "[data-stock='in']",
    ".status-available", ".stock-available",
]
_STOCK_OUT_SELECTORS = [
    ".out-of-stock", "[class*='out-of-stock']", "[class*='outofstock']",
    "[data-availability='unavailable']", "[data-stock='out']",
    ".status-unavailable", ".stock-unavailable",
]
_STOCK_CONTAINER_SELECTORS = [
    ".availability", ".stock", ".product-availability",
    ".product-stock", ".product-status",
    "[class*='availability']", "[class*='stock-status']",
    "[itemprop='availability']",
]
_STOCK_POSITIVE = frozenset({
    "в наявності", "є в наявності", "in stock", "instock",
    "available", "на складі", "є на складі", "є в нас",
    "наявний", "наявна",
})
_STOCK_NEGATIVE = frozenset({
    "немає в наявності", "нема в наявності", "відсутній", "відсутня",
    "not available", "out of stock", "outofstock",
    "немає на складі", "нема на складі", "закінчився", "закінчилась",
    "немає в нас", "нема в нас", "під замовлення",
})


# ---------------------------------------------------------------------------
# Модель результату парсингу
# ---------------------------------------------------------------------------
@dataclass
class PriceResult:
    site: str
    url: str
    article: str
    title: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    in_stock: Optional[bool] = None
    confidence: float = 1.0
    error: Optional[str] = None
    raw_price: Optional[str] = None
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Базовий парсер
# ---------------------------------------------------------------------------
class GenericParser:
    """Універсальний парсер: JSON-LD → Microdata → OpenGraph → CSS."""

    SEARCH_RESULT_SELECTORS = [
        "[data-product-id]", ".product-item", ".product-card", ".catalog-item",
        ".search-result-item", "article.product", "li.product",
    ]
    PRODUCT_LINK_SELECTORS = [
        "a.product-name", "a.product-title", "a.product__name",
        ".product-card a[href]", ".product-item a[href]",
        "h2 a[href]", "h3 a[href]",
    ]
    PRICE_SELECTORS = [
        "[itemprop='price']", "[data-price]",
        ".price", ".product-price", ".price__value", ".price-current",
        ".current-price", ".product__price", ".price-value", "span.price",
    ]
    TITLE_SELECTORS = [
        "[itemprop='name']", "h1.product-name", "h1.product-title", "h1",
        ".product__name", ".product-title",
    ]
    WAIT_FOR_SELECTOR: Optional[str] = None

    def __init__(self, shop_name: str, domain: str):
        self.shop_name = shop_name
        self.domain = domain

    # ---------------------------------------------------------------- helpers --

    @staticmethod
    def _article_variants(article: str) -> list[str]:
        """Варіанти написання артикулу для порівняння з текстом сторінки.

        Лада-артикули типу 2101-2905440 можуть відображатися без роздільника,
        з пробілом або крапкою — нормалізуємо обидва боки перед порівнянням.
        """
        base = article.lower()
        clean = re.sub(r"[-\s.]", "", base)
        variants = [base, clean]
        if re.search(r"[-\s.]", base):
            variants.append(base.replace("-", " ").replace(".", " "))
            variants.append(base.replace("-", ".").replace(" ", "."))
        return list(dict.fromkeys(variants))

    def _article_on_page(self, soup: BeautifulSoup, article: str) -> bool:
        """Перевіряє присутність артикулу (у будь-якому форматі) на сторінці."""
        page_clean = re.sub(r"[-\s.]", "", soup.get_text(" ", strip=True).lower())
        for variant in self._article_variants(article):
            if re.sub(r"[-\s.]", "", variant) in page_clean:
                return True
        return False

    # ---------------------------------------------------------------- public --

    def parse_search_page(self, html: str, article: str, url: str) -> Optional[PriceResult]:
        soup = BeautifulSoup(html, "html.parser")

        result = self._try_jsonld(soup, article, url)
        if result:
            if result.in_stock is None:
                result.in_stock = self._detect_in_stock(soup)
            return result

        card = self._first_product_card(soup, article)
        if card:
            price_text = self._extract_price_text(card, self.PRICE_SELECTORS)
            price, currency, raw = normalize_price(price_text)
            if price is not None:
                title = self._extract_text(card, self.TITLE_SELECTORS) or \
                        self._extract_text(card, ["a"])
                return PriceResult(
                    site=self.shop_name, url=url, article=article,
                    title=clean_text(title), price=price, currency=currency,
                    raw_price=raw, in_stock=self._detect_in_stock(card),
                    confidence=PARSER_CONFIDENCE["search-card"],
                    meta={"source": "search-card"},
                )

        return self._extract_product(soup, article, url)

    def parse_product_page(self, html: str, article: str, url: str) -> Optional[PriceResult]:
        soup = BeautifulSoup(html, "html.parser")
        return self._extract_product(soup, article, url)

    def product_link(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        for sel in self.PRODUCT_LINK_SELECTORS:
            link = soup.select_one(sel)
            if link and link.get("href"):
                return link["href"]
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if any(t in href for t in ("/product", "/goods", "/p/", "/item", "/tovar")):
                return href
        return None

    # --------------------------------------------------------------- private --

    def _extract_product(self, soup: BeautifulSoup, article: str, url: str) -> Optional[PriceResult]:
        # 1) JSON-LD
        result = self._try_jsonld(soup, article, url)
        if result:
            if result.in_stock is None:
                result.in_stock = self._detect_in_stock(soup)
            return result

        # 2) Microdata
        md = self._parse_microdata(soup)
        if md and md.get("price") and self._article_on_page(soup, article):
            in_stock = md.get("in_stock") or self._detect_in_stock(soup)
            return PriceResult(
                site=self.shop_name, url=url, article=article,
                title=md.get("title"), price=md["price"],
                currency=md.get("currency"), raw_price=md.get("raw"),
                in_stock=in_stock,
                confidence=PARSER_CONFIDENCE["microdata"],
                meta={"source": "microdata"},
            )

        # 3) OpenGraph
        og_price = self._meta_content(soup, "product:price:amount", "og:price:amount")
        if og_price:
            price, currency, raw = normalize_price(og_price)
            og_currency = self._meta_content(soup, "product:price:currency", "og:price:currency")
            if price is not None and self._article_on_page(soup, article):
                return PriceResult(
                    site=self.shop_name, url=url, article=article,
                    title=self._meta_content(soup, "og:title") or
                          self._extract_text(soup, self.TITLE_SELECTORS),
                    price=price, currency=og_currency or currency, raw_price=raw,
                    in_stock=self._detect_in_stock(soup),
                    confidence=PARSER_CONFIDENCE["opengraph"],
                    meta={"source": "opengraph"},
                )

        # 4) CSS — спочатку шукаємо в основному блоці товару (поряд з кнопкою купити),
        #    потім fallback на всю сторінку зі знятим шумом
        main_block = self._find_main_price_block(soup)
        for root, source_name in [(main_block, "css-main-block"), (None, "css")]:
            if root is None and source_name == "css":
                root = self._stripped_soup(soup)
            if root is None:
                continue
            price_text = self._extract_price_text(root, self.PRICE_SELECTORS)
            if price_text:
                price, currency, raw = normalize_price(price_text)
                if price is not None:
                    if not self._article_on_page(soup, article):
                        return None
                    return PriceResult(
                        site=self.shop_name, url=url, article=article,
                        title=self._extract_text(soup, self.TITLE_SELECTORS),
                        price=price, currency=currency, raw_price=raw,
                        in_stock=self._detect_in_stock(main_block or soup),
                        confidence=PARSER_CONFIDENCE["css"],
                        meta={"source": source_name},
                    )

        return None

    def _try_jsonld(self, soup: BeautifulSoup, article: str, url: str) -> Optional[PriceResult]:
        data = self._parse_jsonld(soup)
        if not data:
            return None
        if not self._article_on_page(soup, article):
            log.debug(f"[{self.domain}] JSON-LD: артикул {article!r} відсутній на сторінці")
            return None
        return PriceResult(
            site=self.shop_name, url=url, article=article,
            title=data.get("title"), price=data.get("price"),
            currency=data.get("currency"), in_stock=data.get("in_stock"),
            raw_price=data.get("raw"),
            confidence=PARSER_CONFIDENCE["json-ld"],
            meta={"source": "json-ld"},
        )

    def _first_product_card(self, soup: BeautifulSoup, article: str) -> Optional[Tag]:
        cards = []
        for sel in self.SEARCH_RESULT_SELECTORS:
            cards.extend(soup.select(sel))
        if not cards:
            return None
        variants = self._article_variants(article)
        for card in cards:
            card_clean = re.sub(r"[-\s.]", "", card.get_text(" ", strip=True).lower())
            for v in variants:
                if re.sub(r"[-\s.]", "", v) in card_clean:
                    return card
        return None

    def _find_main_price_block(self, soup: BeautifulSoup) -> Optional[Tag]:
        """Повертає DOM-контейнер основного блоку товару.

        Алгоритм:
        1. Знайти кнопку "купити/в кошик" (CSS-якір або текст).
        2. Піднятися по DOM до батька, що містить елемент ціни.
        3. Fallback — знайти h1 і піднятися аналогічно.
        """
        # --- CSS-якорі кнопки ---
        for sel in _BUY_ANCHOR_SELECTORS:
            try:
                btn = soup.select_one(sel)
            except Exception:
                continue
            if btn:
                block = self._climb_to_price_container(btn)
                if block is not None:
                    return block

        # --- Текстовий пошук кнопки ---
        for tag in soup.find_all(["button", "a"]):
            text = clean_text(tag.get_text(" ") or "").lower()
            if any(kw in text for kw in _BUY_BUTTON_TEXTS):
                block = self._climb_to_price_container(tag)
                if block is not None:
                    return block

        # --- Fallback: h1 ---
        h1 = soup.find("h1")
        if h1:
            block = self._climb_to_price_container(h1, max_depth=4)
            if block is not None:
                return block

        return None

    def _climb_to_price_container(self, start: Tag, max_depth: int = _BUY_CONTEXT_DEPTH) -> Optional[Tag]:
        """Піднімається по DOM від start; повертає перший батько, що містить елемент ціни."""
        parent = start.parent
        for _ in range(max_depth):
            if not isinstance(parent, Tag) or parent.name in ("html", "body", "[document]"):
                break
            for sel in self.PRICE_SELECTORS:
                try:
                    if parent.select_one(sel):
                        return parent
                except Exception:
                    pass
            parent = parent.parent
        return None

    def _stripped_soup(self, soup: BeautifulSoup) -> BeautifulSoup:
        """Повертає копію soup без шумових секцій (каруселі, sidebar, footer…)."""
        clean = BeautifulSoup(str(soup), "html.parser")
        for sel in _NOISE_SELECTORS:
            try:
                for el in clean.select(sel):
                    el.decompose()
            except Exception:
                pass
        return clean

    def _extract_text(self, root, selectors: list[str]) -> Optional[str]:
        for sel in selectors:
            el = root.select_one(sel)
            if not el:
                continue
            for attr in ("content", "data-price", "value"):
                if el.has_attr(attr) and el[attr].strip():
                    return el[attr].strip()
            text = clean_text(el.get_text(" "))
            if text:
                return text
        return None

    def _extract_price_text(self, root, selectors: list[str]) -> Optional[str]:
        """Повертає перший текст ціни, ігноруючи закреслені/старі елементи."""
        for sel in selectors:
            try:
                elements = root.select(sel)
            except Exception:
                continue
            for el in elements:
                if self._is_old_price(el):
                    continue
                for attr in ("content", "data-price", "value"):
                    if el.has_attr(attr) and el[attr].strip():
                        return el[attr].strip()
                text = clean_text(el.get_text(" "))
                if text:
                    return text
        return None

    @staticmethod
    def _is_old_price(el: Tag) -> bool:
        if el.name in _OLD_PRICE_TAGS:
            return True
        for parent in el.parents:
            if not isinstance(parent, Tag):
                continue
            if parent.name in _OLD_PRICE_TAGS:
                return True
            cls_list = parent.get("class") or []
            if isinstance(cls_list, str):
                cls_list = cls_list.split()
            if any(c.lower() in _OLD_PRICE_CLASSES for c in cls_list):
                return True
        return False

    def _detect_in_stock(self, root) -> Optional[bool]:
        for sel in _STOCK_IN_SELECTORS:
            try:
                if root.select_one(sel):
                    return True
            except Exception:
                pass
        for sel in _STOCK_OUT_SELECTORS:
            try:
                if root.select_one(sel):
                    return False
            except Exception:
                pass
        for container_sel in _STOCK_CONTAINER_SELECTORS:
            try:
                el = root.select_one(container_sel)
            except Exception:
                continue
            if not el:
                continue
            text = clean_text(el.get_text()).lower()
            for phrase in _STOCK_NEGATIVE:
                if phrase in text:
                    return False
            for phrase in _STOCK_POSITIVE:
                if phrase in text:
                    return True
        return None

    def _meta_content(self, soup: BeautifulSoup, *names: str) -> Optional[str]:
        for name in names:
            tag = soup.find("meta", attrs={"property": name}) or \
                  soup.find("meta", attrs={"name": name})
            if tag and tag.get("content"):
                return tag["content"].strip()
        return None

    def _parse_jsonld(self, soup: BeautifulSoup) -> Optional[dict]:
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            candidates = []
            if isinstance(data, list):
                candidates.extend(data)
            elif isinstance(data, dict):
                candidates.extend(data.get("@graph", [data]))
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                t = item.get("@type")
                if isinstance(t, list):
                    t = next((x for x in t if "product" in str(x).lower()), None)
                if not t or "product" not in str(t).lower():
                    continue
                offers = item.get("offers")
                if isinstance(offers, list):
                    offers = offers[0] if offers else None
                if not isinstance(offers, dict):
                    continue
                raw_price = offers.get("price") or offers.get("lowPrice")
                if raw_price is None:
                    continue
                price, currency, raw = normalize_price(str(raw_price))
                if price is None:
                    continue
                avail = (offers.get("availability") or "").lower()
                in_stock = (
                    True if "instock" in avail
                    else False if ("outofstock" in avail or "discontinued" in avail)
                    else None
                )
                return {
                    "price": price,
                    "currency": offers.get("priceCurrency") or currency,
                    "title": item.get("name"),
                    "in_stock": in_stock,
                    "raw": raw,
                }
        return None

    def _parse_microdata(self, soup: BeautifulSoup) -> Optional[dict]:
        el = soup.find(attrs={"itemprop": "price"})
        if not el:
            return None
        raw_price = el.get("content") or el.get_text(" ", strip=True)
        price, currency, raw = normalize_price(raw_price)
        if price is None:
            return None
        cur_el = soup.find(attrs={"itemprop": "priceCurrency"})
        if cur_el:
            currency = cur_el.get("content") or cur_el.get_text(strip=True) or currency
        title_el = soup.find(attrs={"itemprop": "name"})
        avail_el = soup.find(attrs={"itemprop": "availability"})
        in_stock = None
        if avail_el:
            av = (avail_el.get("content") or avail_el.get_text(strip=True) or "").lower()
            if "instock" in av:
                in_stock = True
            elif "outofstock" in av or "discontinued" in av:
                in_stock = False
        return {
            "price": price, "currency": currency,
            "title": clean_text(title_el.get_text()) if title_el else None,
            "in_stock": in_stock, "raw": raw,
        }
