# Скрапер цін автозапчастин (Playwright)

Модуль для збору цін на автозапчастини за артикулом з популярних українських інтернет-магазинів. Використовує **Playwright** — справжній браузер Chromium, який повноцінно виконує JavaScript і дозволяє обходити антибот-захист та парсити SPA-застосунки (Розетка, Prom тощо).

## Структура проєкту

```
price_scraper/
├── scraper.py          # Головний модуль + CLI
├── browser.py          # Менеджер Playwright з обходом антибота
├── utils.py            # Нормалізація цін
├── sites/
│   └── __init__.py     # GenericParser + парсери для конкретних магазинів
├── requirements.txt
├── setup.sh            # Скрипт встановлення для Linux/macOS
└── setup.bat           # Скрипт встановлення для Windows
```

## Встановлення

### Автоматично

**Linux/macOS:**
```bash
chmod +x setup.sh
./setup.sh
```

**Windows:**
```cmd
setup.bat
```

Скрипт зробить:
1. Створить віртуальне середовище у `./venv`
2. Встановить Python-залежності (`playwright`, `beautifulsoup4`, `lxml`)
3. Завантажить Chromium для Playwright
4. На Linux — встановить системні бібліотеки для браузера

### Вручну

```bash
# 1. Створити venv
python3 -m venv venv
source venv/bin/activate           # Linux/Mac
# venv\Scripts\activate            # Windows

# 2. Поставити пакети
pip install -r requirements.txt

# 3. Завантажити Chromium
playwright install chromium

# 4. (Тільки Linux) Системні бібліотеки
playwright install-deps chromium
```

## Використання

### Активуй venv перед запуском

```bash
source venv/bin/activate    # Linux/Mac
venv\Scripts\activate       # Windows
```

### CLI

```bash
# Просто шукаємо артикул
python scraper.py 1K0407151BC

# Зберегти результати у JSON
python scraper.py 1K0407151BC --json results.json

# Запустити з вікном браузера (дебаг — видно що відбувається)
python scraper.py 1K0407151BC --headed

# Збільшити паралельність (швидше, але більше пам'яті)
python scraper.py 1K0407151BC --concurrency 5

# Через проксі
python scraper.py 1K0407151BC --proxy http://user:pass@host:port

# Або через змінну середовища:
export PROXY_URL=http://user:pass@host:port
python scraper.py 1K0407151BC

# Детальний лог
python scraper.py 1K0407151BC -v
```

### Програмно

```python
import asyncio
from scraper import PriceScraper

async def main():
    scraper = PriceScraper(
        headless=True,
        concurrency=3,
        proxy=None,  # або "http://user:pass@host:port"
    )
    results = await scraper.scrape_article("1K0407151BC")
    for r in results:
        if r.price:
            print(f"{r.site}: {r.price} {r.currency} — {r.url}")
        else:
            print(f"{r.site}: ✗ {r.error}")

asyncio.run(main())
```

### Як FastAPI/Flask endpoint

```python
from fastapi import FastAPI
from scraper import PriceScraper

app = FastAPI()

@app.get("/prices/{article}")
async def get_prices(article: str):
    scraper = PriceScraper(concurrency=4)
    results = await scraper.scrape_article(article)
    return [r.to_dict() for r in results]
```

## Як працює обхід антибота

`browser.py` робить кілька речей одночасно:

1. **Аргументи запуску Chromium:** `--disable-blink-features=AutomationControlled` прибирає основну ознаку автоматизації.
2. **Stealth JS-патч (`STEALTH_JS`)** інжектується в кожну сторінку **до** її виконання. Він перевизначає:
   - `navigator.webdriver` → `undefined`
   - `navigator.plugins` → реалістичний список
   - `navigator.languages` → `["uk-UA", "uk", ...]`
   - `navigator.hardwareConcurrency` → 8
   - `window.chrome.runtime` → присутнє
   - `WebGL vendor/renderer` → нормальний Intel
   - Виправляє `permissions.query` для нотифікацій
3. **Реалістичний контекст:** український UA, locale `uk-UA`, timezone `Europe/Kyiv`, viewport 1920×1080.
4. **Persistent context:** куки зберігаються у `~/.price_scraper_state`. На наступному запуску магазини «впізнають» нас як повторного відвідувача — менше шансів отримати блок.
5. **Виявлення челенджу:** якщо на сторінці заголовок `"Just a moment..."` або `#challenge-form` (Cloudflare) — чекаємо до 15 секунд, поки автоматичний челендж пройде.
6. **Людська поведінка:** імітація скролу мишею з рандомними паузами, рандомний User-Agent, рандомні таймінги.
7. **Підтримка проксі:** у `--proxy` або в `PROXY_URL`. Для серйозних магазинів типу Розетки бажано використовувати резидентські проксі.

## Як працює парсинг SPA

Playwright чекає JS-рендер сам, але для надійності в `GenericParser.WAIT_FOR_SELECTOR` можна вказати селектор, без якого нема сенсу парсити. Наприклад, для Розетки це `.goods-tile__price-value` — поки він не з'явиться, чекаємо. Після цього емулюємо скрол (для тригера lazy-load) і робимо паузу 400-900 мс для остаточного рендеру.

## Як працює гнучкий парсинг

`GenericParser` шукає ціну в чотири проходи — від найнадійнішого до найслабшого:

1. **JSON-LD** (`<script type="application/ld+json">` з `Schema.org/Product`) — стандарт, який вимагає Google від інтернет-магазинів. Працює на більшості сучасних сайтів.
2. **Microdata** (`itemprop="price"`) — старіший стандарт мікророзмітки.
3. **OpenGraph** (`<meta property="product:price:amount">`) — мета-теги.
4. **CSS-селектори** — типові класи `.price`, `.product-price`, `[data-price]` тощо.

**Тому модуль працює на більшості магазинів без написання коду спеціально під них.** Достатньо додати запис у `SHOPS`.

## Як додати новий магазин

### Якщо сайт стандартний (працює universal parser):

В `scraper.py` додати у список `SHOPS`:
```python
{
    "name": "MyShop",
    "search_url": "https://myshop.ua/search?q={q}",
    "domain": "myshop.ua",
},
```

Все. Запусти `python scraper.py 1K0407151BC` — якщо знаходить, готово.

### Якщо сайт нестандартний:

У `sites/__init__.py` додати клас:
```python
class MyShopParser(GenericParser):
    # Чекати цей селектор перед парсингом (для SPA)
    WAIT_FOR_SELECTOR = ".my-price-class"
    # Додати кастомні селектори (вони матимуть пріоритет)
    PRICE_SELECTORS = [".my-price-class"] + GenericParser.PRICE_SELECTORS
    PRODUCT_LINK_SELECTORS = [".my-link"] + GenericParser.PRODUCT_LINK_SELECTORS

SITE_PARSERS["myshop.ua"] = MyShopParser
```

## Магазини за замовчуванням

| Магазин | Парсер |
|---|---|
| Exist.ua | ExistParser |
| Rozetka | RozetkaParser |
| Prom.ua | PromParser (бере мінімальну ціну з пропозицій) |
| Autoluks, Avtozapchasti, Autopiter, Avtoto, ZAP, Avto.pro, Bamper | Generic |

## Що варто згадати в дипломі

- **Обхід антибот-захисту.** Stealth-патч, persistent context, ротація User-Agent, імітація людських дій. Це активна тема в research (наприклад, fingerprinting через WebGL/Canvas/Audio API).
- **SPA-рендеринг.** На відміну від простого HTTP-скрапера, Playwright виконує JS і дочікується рендеру. Розетка та Prom — це SPA на Angular/React, без браузера ціни не побачиш.
- **Гнучка архітектура.** Чотирирівневий fallback (JSON-LD → microdata → OG → CSS) дозволяє підтримувати нові магазини без зміни коду.
- **Асинхронність + browser context pool.** Один Playwright обслуговує всі магазини паралельно через семафор.
- **Обмеження.** Найжорсткіші захисти (PerimeterX, DataDome зі складними капчами) можуть вимагати сервісів типу 2Captcha. Це описують у розділі обмежень.
- **Юридичний аспект.** Скрапінг публічно доступних цін з конкурентів в Україні не заборонений, але треба згадати про `robots.txt` та доцільність ToS-аналізу.

## Розширення для диплому

- БД для історії цін (PostgreSQL/SQLite) → графіки динаміки цін
- Веб-інтерфейс (FastAPI + React/Vue)
- Сповіщення в Telegram, коли конкурент демпінгує
- Кешування через Redis на 1-2 години, щоб не довбати магазини
- Аналітика: медіана/мінімум/максимум по ринку для конкретного артикула
