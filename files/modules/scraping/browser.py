"""
Менеджер браузера на основі Playwright з обходом антибота.

Що тут реалізовано для маскування від детекторів типу Cloudflare/DataDome:
  • playwright-stealth: приховує navigator.webdriver та інші ознаки
  • Реалістичний User-Agent + viewport + locale + timezone
  • Блокування зайвих ресурсів (картинок, шрифтів, аналітики)
  • Persistent context — куки/локалсторадж зберігаються між запусками
  • Затримки між діями, що імітують людську поведінку
  • Підтримка проксі
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Route,
)


log = logging.getLogger("scraper.browser")

# Дані браузера зберігаємо у папці проєкту
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = _PROJECT_ROOT / "data" / "browser_state"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
]

BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}
BLOCKED_URL_PATTERNS = [
    "google-analytics.com", "googletagmanager.com", "facebook.net",
    "doubleclick.net", "googlesyndication.com", "hotjar.com",
    "yandex.ru/metrika", "mc.yandex.ru", "criteo.com", "adservice.google",
    "twitter.com/i/adsct", "amplitude.com", "segment.io",
]

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'PDF Viewer', filename: 'internal-pdf-viewer' },
        { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer' },
    ]
});
Object.defineProperty(navigator, 'languages', {
    get: () => ['uk-UA', 'uk', 'ru', 'en-US', 'en']
});
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
if (!window.chrome) { window.chrome = { runtime: {} }; }
const origQuery = window.navigator.permissions && window.navigator.permissions.query;
if (origQuery) {
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : origQuery(parameters)
    );
}
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.apply(this, [parameter]);
};
"""


class BrowserManager:
    """Менеджер браузера з обходом антибот-захисту."""

    def __init__(
        self,
        headless: bool = True,
        proxy: Optional[str] = None,
        block_resources: bool = True,
        persistent: bool = True,
    ):
        self.headless = headless
        self.proxy = proxy or os.environ.get("PROXY_URL")
        self.block_resources = block_resources
        self.persistent = persistent

        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self):
        self._pw = await async_playwright().start()

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--no-sandbox",
            "--disable-web-security",
            "--disable-dev-shm-usage",
        ]

        proxy_config = None
        if self.proxy:
            from urllib.parse import urlparse
            p = urlparse(self.proxy)
            proxy_config = {"server": f"{p.scheme}://{p.hostname}:{p.port}"}
            if p.username:
                proxy_config["username"] = p.username
            if p.password:
                proxy_config["password"] = p.password
            log.info(f"Використовую проксі: {p.hostname}:{p.port}")

        user_agent = random.choice(USER_AGENTS)

        if self.persistent:
            STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            self._context = await self._pw.chromium.launch_persistent_context(
                user_data_dir=str(STORAGE_DIR),
                headless=self.headless,
                args=launch_args,
                proxy=proxy_config,
                user_agent=user_agent,
                viewport={"width": 1920, "height": 1080},
                locale="uk-UA",
                timezone_id="Europe/Kyiv",
                color_scheme="light",
                ignore_https_errors=True,
            )
            self._browser = None
        else:
            self._browser = await self._pw.chromium.launch(
                headless=self.headless,
                args=launch_args,
                proxy=proxy_config,
            )
            self._context = await self._browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1920, "height": 1080},
                locale="uk-UA",
                timezone_id="Europe/Kyiv",
                ignore_https_errors=True,
            )

        await self._context.add_init_script(STEALTH_JS)

        if self.block_resources:
            await self._context.route("**/*", self._route_handler)

        return self

    async def __aexit__(self, *exc):
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception as e:
            log.debug(f"Помилка закриття браузера: {e}")

    async def _route_handler(self, route: Route):
        req = route.request
        if req.resource_type in BLOCKED_RESOURCE_TYPES:
            await route.abort()
            return
        if any(pattern in req.url for pattern in BLOCKED_URL_PATTERNS):
            await route.abort()
            return
        await route.continue_()

    async def new_page(self) -> Page:
        assert self._context is not None
        page = await self._context.new_page()
        page.set_default_timeout(8_000)
        page.set_default_navigation_timeout(12_000)
        return page

    async def fetch_html(
        self,
        url: str,
        wait_for_selector: Optional[str] = None,
        wait_until: str = "domcontentloaded",
        scroll: bool = True,
    ) -> Optional[str]:
        page = await self.new_page()
        try:
            log.info(f"[browser] завантаження {url}")
            try:
                await page.goto(url, wait_until=wait_until)
            except Exception as e:
                log.info(f"[browser] таймаут ({url}), fallback до 'commit'")
                try:
                    await page.goto(url, wait_until="commit")
                except Exception:
                    log.info(f"[browser] не вдалося завантажити {url}")
                    return None

            if await self._is_challenge_page(page):
                log.warning(f"Антибот-челендж на {url}, чекаю…")
                await self._wait_for_challenge(page)

            if wait_for_selector:
                try:
                    await page.wait_for_selector(
                        wait_for_selector, timeout=5_000, state="attached"
                    )
                except Exception:
                    log.debug(f"Селектор {wait_for_selector} не з'явився на {url}")

            if scroll:
                await self._human_scroll(page)

            await page.wait_for_timeout(random.randint(200, 500))
            return await page.content()
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def _is_challenge_page(self, page: Page) -> bool:
        try:
            title = (await page.title()).lower()
            if any(t in title for t in ("just a moment", "checking your browser", "captcha")):
                return True
            if await page.locator("#challenge-form, #cf-challenge-running").count() > 0:
                return True
        except Exception:
            pass
        return False

    async def _wait_for_challenge(self, page: Page, max_wait: int = 8):
        for _ in range(max_wait):
            await page.wait_for_timeout(1000)
            if not await self._is_challenge_page(page):
                log.info("Челендж пройдено")
                return
        log.warning("Челендж не пройшов автоматично")

    async def _human_scroll(self, page: Page):
        try:
            for _ in range(random.randint(1, 2)):
                await page.mouse.wheel(0, random.randint(300, 700))
                await page.wait_for_timeout(random.randint(100, 200))
        except Exception:
            pass
