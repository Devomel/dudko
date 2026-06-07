"""
Пошук URL магазинів через пошукові системи.

Черговість: DuckDuckGo HTML (менш агресивний щодо ботів) → Bing → Google.
Повертає по одному URL на унікальний домен.
"""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import quote_plus, urlparse, parse_qs, unquote

from bs4 import BeautifulSoup


log = logging.getLogger("scraper.search")

BLACKLIST_DOMAINS = {
    "youtube.com", "youtu.be", "wikipedia.org", "facebook.com", "instagram.com",
    "twitter.com", "x.com", "tiktok.com", "reddit.com", "linkedin.com",
    "google.com", "duckduckgo.com", "bing.com", "yandex.ua", "yandex.ru",
    "drom.ua", "auto.ria.com",
    "wikiwand.com", "habr.com", "stackoverflow.com",
    "forum.auto.ria.com", "forum.drom.ru",
}

# Регіональні домени пошуковиків (google.com.ua, bing.com.ua, google.co.uk тощо)
_SEARCH_ENGINE_RE = re.compile(r"^(www\.)?(google|bing|yahoo|duckduckgo|yandex)\.")

BLACKLIST_PATH_PATTERNS = [
    "/news/", "/article/", "/blog/", "/forum/", "/video",
    ".pdf", ".doc", ".jpg", ".png",
]

# Артикул Лади/ВАЗ: 4-6 цифр, дефіс, 6-8 цифр (напр. 2101-2905440, 21080-3501070)
_LADA_OEM_RE = re.compile(r"^\d{4,6}-\d{6,8}$")


def _is_lada_article(article: str) -> bool:
    return bool(_LADA_OEM_RE.match(article.strip()))


def normalize_domain(url: str) -> str:
    """Приводить домен до канонічної форми (без www.)."""
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def is_useful_url(url: str) -> bool:
    if not url or not url.startswith(("http://", "https://")):
        return False
    domain = normalize_domain(url)
    if not domain:
        return False
    if domain in BLACKLIST_DOMAINS:
        return False
    for bad in BLACKLIST_DOMAINS:
        if domain.endswith("." + bad):
            return False
    if _SEARCH_ENGINE_RE.match(domain):
        return False
    path = urlparse(url).path.lower()
    for pat in BLACKLIST_PATH_PATTERNS:
        if pat in path:
            return False
    return True


def _parse_duckduckgo(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for a in soup.select("a.result__a, a.result__url, h2.result__title a"):
        href = a.get("href", "").strip()
        if not href:
            continue
        if href.startswith("/l/") or href.startswith("//duckduckgo.com/l/"):
            try:
                parsed = urlparse(
                    href if href.startswith("http")
                    else "https:" + href if href.startswith("//")
                    else "https://duckduckgo.com" + href
                )
                params = parse_qs(parsed.query)
                if "uddg" in params:
                    href = unquote(params["uddg"][0])
            except Exception:
                continue
        if href.startswith("//"):
            href = "https:" + href
        urls.append(href)
    return urls


def _parse_bing(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for a in soup.select("li.b_algo h2 a, li.b_algo a.tilk"):
        href = a.get("href", "").strip()
        if href and href.startswith("http"):
            urls.append(href)
    return urls


def _parse_google(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/url?"):
            try:
                params = parse_qs(urlparse(href).query)
                if "q" in params:
                    href = params["q"][0]
            except Exception:
                continue
        if href.startswith("http"):
            urls.append(href)
    return urls


async def find_shop_urls(
    browser,
    article: str,
    limit: int = 5,
    extra_query: str = "купити автозапчастина",
) -> list[str]:
    """Знаходить URL інтернет-магазинів за артикулом через пошукові системи."""
    if _is_lada_article(article):
        query = f"{article} ВАЗ Лада купити запчастина Україна"
    else:
        query = f"{article} {extra_query} Україна"

    search_engines = [
        ("DuckDuckGo",
         f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&kl=ua-uk",
         _parse_duckduckgo),
        ("Bing",
         f"https://www.bing.com/search?q={quote_plus(query)}&cc=ua",
         _parse_bing),
        ("Google",
         f"https://www.google.com/search?q={quote_plus(query)}&hl=uk&gl=ua",
         _parse_google),
    ]

    all_urls: list[str] = []
    for name, search_url, parse_fn in search_engines:
        log.info(f"[search] Шукаю через {name}: {query}")
        try:
            html = await browser.fetch_html(search_url, scroll=False)
            if not html:
                log.warning(f"[search] {name} не повернув HTML")
                continue
            urls = parse_fn(html)
            log.info(f"[search] {name}: {len(urls)} сирих результатів")
            all_urls.extend(urls)
            unique = len({normalize_domain(u) for u in all_urls if is_useful_url(u)})
            if unique >= limit:
                break
        except Exception as e:
            log.warning(f"[search] {name} впав: {type(e).__name__}: {e}")

    seen: set[str] = set()
    result: list[str] = []
    for url in all_urls:
        if not is_useful_url(url):
            continue
        domain = normalize_domain(url)
        if domain in seen:
            continue
        seen.add(domain)
        result.append(url)
        if len(result) >= limit:
            break

    log.info(f"[search] Знайдено {len(result)} унікальних магазинів")
    for u in result:
        log.info(f"  → {u}")
    return result
