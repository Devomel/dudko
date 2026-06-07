"""
AI-парсер цін через OpenAI.

Замість детерміністичних CSS-селекторів/JSON-LD/мікродати —
очищає HTML до читабельного тексту і передає до LLM,
яка сама знаходить ціну та повертає строгий JSON.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

from bs4 import BeautifulSoup, Comment
from openai import AsyncOpenAI

from modules.scraping.parsers.base import PriceResult, PARSER_CONFIDENCE
from utils import clean_text

log = logging.getLogger("scraper.ai_parser")

_MODEL = "gpt-4o-mini"
_MAX_CHARS = 8_000

_SYSTEM_PROMPT = """\
You are a price extraction assistant for an auto parts price monitoring system.
Given a webpage text (search results or product page), extract the current selling price \
for the specified part number.

Respond with ONLY valid JSON — no markdown, no explanation:
{
  "price": <number or null>,
  "currency": <"UAH" | "USD" | "EUR" | null>,
  "in_stock": <true | false | null>,
  "title": <string or null>
}

Rules:
- Extract the CURRENT price, not old/crossed-out/was price
- If multiple products are listed, find the one matching the article
- price must be a plain number (e.g. 1234.56), not a string
- currency defaults to "UAH" for Ukrainian sites (грн / ₴)
- in_stock: true if available, false if out of stock, null if unknown
- title: the product name (short, without price or stock info)
- If no price is found, set price to null
"""

_NOISE_TAGS = frozenset({
    "script", "style", "noscript", "svg", "canvas", "iframe",
    "head", "meta", "link", "base", "template",
})
_NOISE_SELECTORS = [
    "nav", "footer", "header", "aside",
    "[class*='sidebar']", "[class*='cookie']",
    "[class*='popup']",  "[class*='modal']",
    "[class*='banner']", "[class*='advert']",
    "[class*='related']", "[class*='similar']",
    "[class*='carousel']", "[class*='slider']",
    "[class*='widget']",
]


def _html_to_text(html: str) -> str:
    """Strips HTML to clean readable text, removing scripts/styles/noise sections."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(list(_NOISE_TAGS)):
        tag.decompose()

    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        c.extract()

    for sel in _NOISE_SELECTORS:
        try:
            for el in soup.select(sel):
                el.decompose()
        except Exception:
            pass

    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)

    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS]

    return text.strip()


class AiPriceParser:
    """Парсер цін на базі OpenAI: HTML → очищений текст → LLM → PriceResult."""

    def __init__(self, shop_name: str, domain: str, api_key: str = ""):
        self.shop_name = shop_name
        self.domain = domain
        self._client = AsyncOpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY", ""))

    async def parse(self, html: str, article: str, url: str) -> Optional[PriceResult]:
        """Cleans HTML, sends to OpenAI, parses JSON response into PriceResult."""
        page_text = _html_to_text(html)
        if not page_text:
            return PriceResult(
                site=self.shop_name, url=url, article=article,
                error="порожня сторінка після очищення HTML",
            )

        try:
            response = await self._client.chat.completions.create(
                model=_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Part number to find: {article}\n\n"
                            f"Page URL: {url}\n\n"
                            f"Page content:\n{page_text}"
                        ),
                    },
                ],
                temperature=0,
                max_tokens=200,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            log.error(f"[{self.domain}] OpenAI error: {e}")
            return PriceResult(
                site=self.shop_name, url=url, article=article,
                error=f"OpenAI: {type(e).__name__}: {e}",
            )

        raw_json = (response.choices[0].message.content or "").strip()
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            log.error(f"[{self.domain}] invalid JSON from AI: {raw_json!r}")
            return PriceResult(
                site=self.shop_name, url=url, article=article,
                error=f"AI повернув невалідний JSON: {e}",
            )

        price = data.get("price")
        if price is not None:
            try:
                price = float(price)
            except (TypeError, ValueError):
                price = None

        title = data.get("title")
        if title:
            title = clean_text(str(title)) or None

        return PriceResult(
            site=self.shop_name,
            url=url,
            article=article,
            title=title,
            price=price,
            currency=data.get("currency") or "UAH",
            in_stock=data.get("in_stock"),
            confidence=PARSER_CONFIDENCE["ai"],
            meta={"source": "ai", "model": _MODEL},
        )
