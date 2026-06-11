# Система моніторингу цін на автозапчастини

Повностекова система для збору та аналізу цін конкурентів на ринку автозапчастин. Складається з чотирьох компонентів:

| Компонент | Технологія | Порт |
|-----------|-----------|------|
| `db/` | PostgreSQL 16 | 5433 |
| `api/` | FastAPI + asyncpg | 8000 |
| `frontend/` | Next.js 16 + Tailwind | 3000 |
| `engine/` | Playwright + fuzzy logic | CLI |

---

## Структура проєкту

```
code/
├── docker-compose.yml      # Запуск усіх сервісів
├── api/                    # FastAPI REST API
│   ├── main.py
│   ├── deps.py
│   ├── schemas.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── routers/
│       ├── products.py     # Каталог запчастин
│       ├── scraping.py     # Запуск/моніторинг скрапінгу
│       ├── recommend.py    # Рекомендації цін
│       ├── stats.py        # Статистика
│       └── analytics.py    # Аналітика продажів
├── db/
│   ├── schema.sql          # Повна схема БД
│   ├── seed_products.sql   # Початкові товари
│   └── seed_sales.sql      # Початкова історія продажів
├── engine/                 # Модуль скрапінгу і логіки
│   ├── scraper.py          # CLI скрапера
│   ├── recommend.py        # CLI рекомендацій
│   ├── articles.json       # Список артикулів для пакетного запуску
│   ├── requirements.txt
│   ├── setup.sh / setup.bat
│   ├── run.sh / run.bat
│   ├── recommend.bat
│   └── modules/
│       ├── scraping/       # Playwright + антибот обхід
│       ├── fuzzy/          # Mamdani FIS — нечітка логіка
│       └── db/             # Доступ до PostgreSQL
└── frontend/               # Next.js SPA
    ├── app/
    │   ├── page.tsx        # Дашборд
    │   ├── products/       # Каталог
    │   ├── scraping/       # Управління скрапінгом
    │   └── analytics/      # Аналітика
    └── lib/api.ts          # HTTP-клієнт
```

---

## Швидкий старт — Docker Compose

Найпростіший спосіб запустити всю систему:

### Передумови

- [Docker](https://docs.docker.com/get-docker/) ≥ 24
- [Docker Compose](https://docs.docker.com/compose/) ≥ 2.20

### 1. Змінні середовища (опціонально)

Якщо потрібна функціональність AI-рекомендацій (OpenAI) або проксі для скрапінгу — створіть файл `engine/.env`:

```dotenv
# OpenAI API ключ для AI-рекомендацій (необов'язково)
OPENAI_API_KEY=sk-...

# Проксі для обходу блокувань (необов'язково)
PROXY_URL=http://user:pass@host:port
```

Без `engine/.env` система запуститься в повному обсязі, але без AI-рекомендацій.

### 2. Збірка і запуск

```bash
cd code
docker compose up --build
```

Перший запуск займе 3–7 хвилин (завантаження Chromium всередині API-контейнера).

### 3. Перевірка

Після появи рядка `Application startup complete` у логах:

| Сервіс | URL |
|--------|-----|
| Фронтенд | http://localhost:3000 |
| API (Swagger UI) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |
| PostgreSQL | `localhost:5433` (user/pass/db: `scrapper`) |

### 4. Зупинка

```bash
docker compose down          # зупинити контейнери (дані збережено)
docker compose down -v       # зупинити + видалити volume з БД
```

---

## Локальна розробка (без Docker)

### Передумови

- Python 3.11+
- Node.js 22+
- PostgreSQL 16

### PostgreSQL

Запустіть PostgreSQL та створіть базу:

```sql
CREATE USER scrapper WITH PASSWORD 'scrapper';
CREATE DATABASE scrapper OWNER scrapper;
\c scrapper
\i db/schema.sql
\i db/seed_products.sql
\i db/seed_sales.sql
```

Або через `psql`:

```bash
psql -U postgres -c "CREATE USER scrapper WITH PASSWORD 'scrapper';"
psql -U postgres -c "CREATE DATABASE scrapper OWNER scrapper;"
psql -U scrapper -d scrapper -f db/schema.sql
psql -U scrapper -d scrapper -f db/seed_products.sql
psql -U scrapper -d scrapper -f db/seed_sales.sql
```

### API (FastAPI)

```bash
cd api
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
playwright install-deps chromium   # тільки Linux

# Змінні середовища
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=scrapper
export DB_USER=scrapper
export DB_PASSWORD=scrapper

uvicorn main:app --reload --port 8000
```

API доступне на http://localhost:8000, Swagger UI — http://localhost:8000/docs.

### Frontend (Next.js)

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Фронтенд доступний на http://localhost:3000.

### Engine (скрапер — окремо від API)

```bash
cd engine

# Встановлення (один раз)
chmod +x setup.sh && ./setup.sh     # Linux/macOS
# setup.bat                          # Windows

# Активувати venv перед кожним запуском
source venv/bin/activate            # Windows: venv\Scripts\activate
```

---

## Використання engine (CLI)

### Скрапер

```bash
cd engine
source venv/bin/activate

# Одиночний артикул
python scraper.py 1K0407151BC

# Зберегти результат у JSON
python scraper.py 1K0407151BC --json results.json

# Показати вікно браузера (для відлагодження)
python scraper.py 1K0407151BC --headed

# Збільшити паралельність
python scraper.py 1K0407151BC --concurrency 5

# Через проксі
python scraper.py 1K0407151BC --proxy http://user:pass@host:port

# Детальний лог
python scraper.py 1K0407151BC -v
```

Або через обгортку:

```bash
./run.sh 1K0407151BC
./run.sh 1K0407151BC --headed --json results.json
```

### Пакетні рекомендації цін (нечітка логіка)

Відредагуйте `engine/articles.json`:

```json
[
  {
    "article": "1K0407151BC",
    "name": "Тяга стабілізатора VW Golf V",
    "current_price": 2100.00,
    "own_stock_level": 0.2,
    "demand_velocity": 0.7
  }
]
```

Запустіть:

```bash
# Linux/macOS
source venv/bin/activate
python recommend.py

# Windows
recommend.bat

# З параметрами
python recommend.py --articles articles.json --out data/result.json --concurrency 5 -v
```

Результат зберігається у `engine/data/recommendations_YYYYMMDD_HHMMSS.json`.

---

## API — основні ендпоінти

| Метод | URL | Опис |
|-------|-----|------|
| `GET` | `/health` | Перевірка стану |
| `GET` | `/products` | Список товарів |
| `POST` | `/scrape/{article}` | Запустити скрапінг (фон) |
| `GET` | `/scrape/tasks/{task_id}` | Статус завдання |
| `POST` | `/scrape/batch` | Пакетний скрапінг |
| `GET` | `/scrape/{article}/latest` | Остання сесія |
| `GET` | `/scrape/{article}/competitors` | Ціни конкурентів |
| `GET` | `/analytics/sales/monthly` | Продажі по місяцях |
| `GET` | `/analytics/sales/top` | Топ товарів |
| `GET` | `/analytics/stock` | Залишки та прогноз |

Повна документація: http://localhost:8000/docs

---

## Бази даних — ключові таблиці

```
products              — каталог запчастин
product_stock         — поточна ціна та залишок
product_stock_history — повна історія змін ціни/залишку
scraping_sessions     — метадані кожного сеансу скрапінгу
scraping_observations — ціни від конкурентів (по одному запису)
competitor_sources    — реєстр конкурентів та їх надійність
sales_history         — історія продажів
```

---

## Технічні деталі

**Антибот-обхід**: Playwright + Stealth JS-патч (маскування `navigator.webdriver`, реалістичний User-Agent, Persistent browser context, імітація людської поведінки).

**Нечітка логіка**: Два послідовних Mamdani FIS — перший оцінює ринкові умови (наявність у конкурентів, розкид цін), другий коригує на власні умови (залишки, швидкість продажів).

**Парсинг**: Чотирирівневий fallback: JSON-LD → Microdata → OpenGraph → CSS-селектори. Підтримуються Exist.ua, Rozetka, Prom.ua та 7+ інших магазинів.
