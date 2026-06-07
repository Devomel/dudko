from __future__ import annotations

import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from deps import get_db
from schemas import ScrapeRequest, BatchScrapeRequest

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "files"))

from modules.db.scraping import ScrapingRepository
from modules.scraping import PriceScraper, SourceRegistry

router = APIRouter(prefix="/scrape", tags=["scraping"])

# In-memory task store: task_id -> {status, result, error}
_tasks: dict[str, dict] = {}


def _scraping_repo(db=Depends(get_db)) -> ScrapingRepository:
    return ScrapingRepository(db)


async def _run_scrape(task_id: str, article: str, req: ScrapeRequest) -> None:
    _tasks[task_id]["status"] = "running"
    try:
        scraper = PriceScraper(
            headless=not req.headed,
            proxy=req.proxy,
            concurrency=req.concurrency,
            search_limit=req.search_limit,
            registry=SourceRegistry(),
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        )
        bundle = await scraper.scrape_article(article)
        _tasks[task_id]["status"] = "done"
        _tasks[task_id]["result"] = bundle.to_dict()
    except Exception as exc:
        _tasks[task_id]["status"] = "error"
        _tasks[task_id]["error"] = str(exc)


async def _run_batch_scrape(task_id: str, body: BatchScrapeRequest) -> None:
    _tasks[task_id]["status"] = "running"
    req = ScrapeRequest(
        concurrency=body.concurrency,
        search_limit=body.search_limit,
        headed=body.headed,
        proxy=body.proxy,
    )
    for article in body.articles:
        _tasks[task_id]["current"] = article
        sub_id = f"__batch_{task_id}_{article}"
        _tasks[sub_id] = {"status": "pending", "article": article, "result": None, "error": None}
        await _run_scrape(sub_id, article, req)
        sub = _tasks.pop(sub_id, {})
        if sub.get("status") == "done":
            _tasks[task_id]["results"][article] = sub.get("result")
        else:
            _tasks[task_id]["errors"][article] = sub.get("error", "unknown error")
        _tasks[task_id]["done"] += 1
    _tasks[task_id]["status"] = "done"
    _tasks[task_id]["current"] = None


# NOTE: /batch and /tasks must come before /{article} to avoid being shadowed by the path param
@router.post("/batch")
async def start_batch_scrape(
    body: BatchScrapeRequest,
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    if not body.articles:
        raise HTTPException(status_code=422, detail="Список артикулів порожній")
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {
        "status": "pending",
        "articles": body.articles,
        "total": len(body.articles),
        "done": 0,
        "current": None,
        "results": {},
        "errors": {},
        "error": None,
    }
    background_tasks.add_task(_run_batch_scrape, task_id, body)
    return {"task_id": task_id, "articles": body.articles, "total": len(body.articles)}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Завдання не знайдено")
    return task


@router.post("/{article}")
async def start_scrape(
    article: str,
    body: ScrapeRequest = ScrapeRequest(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"status": "pending", "article": article, "result": None, "error": None}
    background_tasks.add_task(_run_scrape, task_id, article, body)
    return {"task_id": task_id, "article": article}


@router.get("/{article}/latest")
async def latest_session(article: str, repo: ScrapingRepository = Depends(_scraping_repo)):
    session = await repo.latest_session(article)
    if not session:
        raise HTTPException(status_code=404, detail="Сесій не знайдено")
    return session


@router.get("/{article}/sessions")
async def sessions_history(
    article: str,
    limit: int = Query(30, ge=1, le=200),
    repo: ScrapingRepository = Depends(_scraping_repo),
):
    return await repo.sessions_history(article, limit=limit)


@router.get("/{article}/competitors")
async def competitor_prices(article: str, repo: ScrapingRepository = Depends(_scraping_repo)):
    return await repo.competitor_prices(article)
