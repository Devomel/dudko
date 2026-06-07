from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from deps import get_db
from schemas import ProductCreate, ProductUpdate, StockSet

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "files"))

from modules.db.products import ProductRepository

router = APIRouter(prefix="/products", tags=["products"])


def _repo(db=Depends(get_db)) -> ProductRepository:
    return ProductRepository(db)


@router.get("")
async def list_products(
    q: Optional[str] = Query(None, description="Пошук по артикулу або назві"),
    category: Optional[str] = None,
    brand: Optional[str] = None,
    active_only: bool = True,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    repo: ProductRepository = Depends(_repo),
):
    if q:
        return await repo.search(q, limit=limit)
    return await repo.list_all(
        active_only=active_only,
        category=category,
        brand=brand,
        limit=limit,
        offset=offset,
    )


@router.get("/comparison")
async def price_comparison_all(repo: ProductRepository = Depends(_repo)):
    return await repo.price_comparison()


@router.get("/{article}")
async def get_product(article: str, repo: ProductRepository = Depends(_repo)):
    product = await repo.get(article)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не знайдено")
    return product


@router.post("", status_code=201)
async def create_product(body: ProductCreate, repo: ProductRepository = Depends(_repo)):
    product_id = await repo.upsert(
        article=body.article,
        name=body.name,
        category=body.category,
        brand=body.brand,
        description=body.description,
    )
    return {"id": product_id, "article": body.article}


@router.put("/{article}")
async def update_product(
    article: str,
    body: ProductUpdate,
    repo: ProductRepository = Depends(_repo),
):
    found = await repo.update_fields(
        article,
        name=body.name,
        description=body.description,
        is_active=body.is_active,
        category=body.category,
        brand=body.brand,
    )
    if not found:
        raise HTTPException(status_code=404, detail="Товар не знайдено")
    return {"ok": True}


@router.post("/{article}/stock")
async def set_stock(
    article: str,
    body: StockSet,
    repo: ProductRepository = Depends(_repo),
):
    try:
        await repo.set_stock(
            article=article,
            price=body.price,
            quantity=body.quantity,
            currency=body.currency,
            warehouse=body.warehouse,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


@router.post("/{article}/activate")
async def activate_product(article: str, repo: ProductRepository = Depends(_repo)):
    try:
        await repo.activate(article)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


@router.delete("/{article}")
async def deactivate_product(article: str, repo: ProductRepository = Depends(_repo)):
    await repo.deactivate(article)
    return {"ok": True}


@router.delete("/{article}/hard")
async def delete_product_hard(article: str, repo: ProductRepository = Depends(_repo)):
    await repo.delete(article)
    return {"ok": True}


@router.get("/{article}/history")
async def price_history(
    article: str,
    limit: int = Query(100, ge=1, le=500),
    repo: ProductRepository = Depends(_repo),
):
    return await repo.price_history(article, limit=limit)


@router.get("/{article}/comparison")
async def price_comparison(article: str, repo: ProductRepository = Depends(_repo)):
    rows = await repo.price_comparison(article)
    if not rows:
        raise HTTPException(status_code=404, detail="Товар не знайдено")
    return rows[0]
