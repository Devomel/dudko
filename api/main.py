from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from deps import startup, shutdown
from routers import products, scraping, recommend, stats, analytics

# Load .env from engine/.env so env vars are available even if server wasn't
# started via start.sh (e.g. during --reload restarts).
_env_file = Path(__file__).parent.parent / "engine" / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# Виводимо логи скрапера в stdout поруч із логами uvicorn
_scraper_log = logging.getLogger("scraper")
_scraper_log.setLevel(logging.INFO)
if not _scraper_log.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S"))
    _scraper_log.addHandler(_h)
    _scraper_log.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup()
    yield
    await shutdown()


app = FastAPI(
    title="Dudko Scrapper API",
    description="REST API для системи моніторингу цін автозапчастин",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(scraping.router)
app.include_router(recommend.router)
app.include_router(stats.router)
app.include_router(analytics.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
