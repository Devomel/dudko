from __future__ import annotations

import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from datetime import datetime, timezone

from schemas import RecommendRequest, RecommendFromSourcesRequest
from deps import get_db

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "files"))

from modules.scraping import PriceScraper, SourceRegistry
from modules.fuzzy import FuzzyPricingEngine
from modules.db.connection import Database
from schema import ScrapingBundle, SourceRecord

router = APIRouter(prefix="/recommend", tags=["recommendations"])

_tasks: dict[str, dict] = {}


async def _get_historical_params(db: Database, article: str) -> tuple[float, float]:
    """Returns (own_stock_level, demand_velocity) from sales_history + product_stock, or (0.5, 0.5) if no data."""
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COALESCE(ps.quantity, 0) AS current_stock,
                COALESCE(
                    (SELECT SUM(sh.quantity)::float / 12
                     FROM sales_history sh
                     WHERE sh.product_id = p.id
                       AND sh.sale_date >= CURRENT_DATE - '365 days'::interval),
                    0
                ) AS monthly_forecast,
                COALESCE(
                    (SELECT SUM(sh.quantity)::float
                     FROM sales_history sh
                     WHERE sh.product_id = p.id
                       AND sh.sale_date >= CURRENT_DATE - '30 days'::interval),
                    0
                ) AS recent_30d_sales
            FROM products p
            LEFT JOIN product_stock ps ON ps.product_id = p.id
            WHERE p.article = $1
            """,
            article,
        )

    if row is None or row["monthly_forecast"] == 0:
        return 0.5, 0.5

    monthly = float(row["monthly_forecast"])
    recent  = float(row["recent_30d_sales"])
    stock   = float(row["current_stock"])

    demand_velocity = min(1.0, recent / monthly)
    own_stock_level = min(1.0, (stock / monthly) / 3.0)

    return own_stock_level, demand_velocity


async def _run_recommend(task_id: str, article: str, req: RecommendRequest, db: Database) -> None:
    _tasks[task_id]["status"] = "running"
    try:
        auto_calculated = False
        stock_level = req.own_stock_level
        demand_vel  = req.demand_velocity

        if stock_level is None or demand_vel is None:
            auto_calculated = True
            db_stock, db_demand = await _get_historical_params(db, article)
            stock_level = db_stock if stock_level is None else stock_level
            demand_vel  = db_demand if demand_vel  is None else demand_vel

        scraper = PriceScraper(
            headless=True,
            concurrency=req.concurrency,
            search_limit=req.search_limit,
            registry=SourceRegistry(),
        )
        bundle: ScrapingBundle = await scraper.scrape_article(article)

        rec = FuzzyPricingEngine().recommend(
            bundle,
            own_stock_level=stock_level,
            demand_velocity=demand_vel,
        )

        current_price = req.current_price
        price_delta = None
        if rec.recommended_price is not None and current_price is not None:
            price_delta = round(rec.recommended_price - current_price, 2)

        competitors = [
            {
                "domain": s.domain,
                "price": s.price,
                "currency": s.currency,
                "in_stock": s.in_stock,
                "url": s.url,
                "title": s.title,
                "effective_weight": s.effective_weight,
            }
            for s in sorted(bundle.valid_sources, key=lambda s: s.price)
        ]

        _tasks[task_id]["status"] = "done"
        _tasks[task_id]["result"] = {
            "article": article,
            "recommendation": {
                "price": rec.recommended_price,
                "delta": price_delta,
                "strategy": rec.strategy,
                "confidence": rec.confidence,
                "reasoning": rec.reasoning,
            },
            "market": {
                "min": rec.market_min,
                "median": rec.market_median,
                "max": rec.market_max,
                "wap": rec.market_wap,
            },
            "fuzzy": {
                "market_position": rec.market_position,
                "own_adjustment": rec.own_adjustment,
                "final_position": rec.fuzzy_position,
            },
            "own_conditions": {
                "stock_level": stock_level,
                "demand_velocity": demand_vel,
                "auto_calculated": auto_calculated,
            },
            "competitors": competitors,
            "scraped_at": bundle.scraped_at,
            "summary": bundle.to_dict()["summary"],
        }
    except Exception as exc:
        _tasks[task_id]["status"] = "error"
        _tasks[task_id]["error"] = str(exc)


@router.post("/from-sources")
async def recommend_from_sources(
    body: RecommendFromSourcesRequest,
    db: Database = Depends(get_db),
):
    """Run fuzzy pricing on caller-supplied sources (no re-scraping)."""
    if not body.sources:
        raise HTTPException(status_code=422, detail="Список джерел порожній")

    stock_level = body.own_stock_level
    demand_vel = body.demand_velocity
    auto_calculated = False

    if stock_level is None or demand_vel is None:
        auto_calculated = True
        db_stock, db_demand = await _get_historical_params(db, body.article)
        stock_level = db_stock if stock_level is None else stock_level
        demand_vel = db_demand if demand_vel is None else demand_vel

    sources = [
        SourceRecord(
            domain=s.domain,
            url=s.url,
            price=s.price,
            currency=s.currency,
            in_stock=s.in_stock,
            confidence=s.confidence,
            source_weight=s.source_weight,
            parser_source=s.parser_source,
            title=s.title,
            raw_price=s.raw_price,
            scraped_at=s.scraped_at or datetime.now(timezone.utc).isoformat(),
        )
        for s in body.sources
    ]

    bundle = ScrapingBundle(
        article=body.article,
        scraped_at=datetime.now(timezone.utc).isoformat(),
        sources=sources,
    )

    rec = FuzzyPricingEngine().recommend(
        bundle,
        own_stock_level=stock_level,
        demand_velocity=demand_vel,
    )

    price_delta = None
    if rec.recommended_price is not None and body.current_price is not None:
        price_delta = round(rec.recommended_price - body.current_price, 2)

    competitors = [
        {
            "domain": s.domain,
            "price": s.price,
            "currency": s.currency,
            "in_stock": s.in_stock,
            "url": s.url,
            "title": s.title,
            "effective_weight": s.effective_weight,
        }
        for s in sorted(bundle.valid_sources, key=lambda s: s.price)
    ]

    return {
        "article": body.article,
        "recommendation": {
            "price": rec.recommended_price,
            "delta": price_delta,
            "strategy": rec.strategy,
            "confidence": rec.confidence,
            "reasoning": rec.reasoning,
        },
        "market": {
            "min": rec.market_min,
            "median": rec.market_median,
            "max": rec.market_max,
            "wap": rec.market_wap,
        },
        "fuzzy": {
            "market_position": rec.market_position,
            "own_adjustment": rec.own_adjustment,
            "final_position": rec.fuzzy_position,
        },
        "own_conditions": {
            "stock_level": stock_level,
            "demand_velocity": demand_vel,
            "auto_calculated": auto_calculated,
        },
        "competitors": competitors,
        "summary": bundle.to_dict()["summary"],
    }


@router.post("/{article}")
async def start_recommend(
    article: str,
    body: RecommendRequest = RecommendRequest(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Database = Depends(get_db),
):
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"status": "pending", "article": article, "result": None, "error": None}
    background_tasks.add_task(_run_recommend, task_id, article, body, db)
    return {"task_id": task_id, "article": article}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Завдання не знайдено")
    return task
