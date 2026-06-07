from __future__ import annotations
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


# ── Products ──────────────────────────────────────────────────────────────────

class ProductCreate(BaseModel):
    article: str
    name: str
    category: Optional[str] = None
    brand: Optional[str] = None
    description: Optional[str] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    category: Optional[str] = None
    brand: Optional[str] = None


class StockSet(BaseModel):
    price: Optional[float] = None
    quantity: int = 0
    currency: str = "UAH"
    warehouse: Optional[str] = None


# ── Scraping ───────────────────────────────────────────────────────────────────

class ScrapeRequest(BaseModel):
    concurrency: int = 6
    search_limit: int = 8
    headed: bool = False
    proxy: Optional[str] = None


class BatchScrapeRequest(BaseModel):
    articles: list[str]
    concurrency: int = 4
    search_limit: int = 8
    headed: bool = False
    proxy: Optional[str] = None


# ── Recommendations ────────────────────────────────────────────────────────────

class RecommendRequest(BaseModel):
    own_stock_level: Optional[float] = None
    demand_velocity: Optional[float] = None
    current_price: Optional[float] = None
    concurrency: int = 6
    search_limit: int = 8


class SourceInput(BaseModel):
    domain: str
    url: str
    price: float
    currency: str = "UAH"
    in_stock: Optional[bool] = None
    confidence: float = 0.82
    source_weight: float = 0.5
    parser_source: str = "ai"
    title: Optional[str] = None
    raw_price: Optional[str] = None
    scraped_at: str = ""


class RecommendFromSourcesRequest(BaseModel):
    article: str
    sources: list[SourceInput]
    own_stock_level: Optional[float] = None
    demand_velocity: Optional[float] = None
    current_price: Optional[float] = None
