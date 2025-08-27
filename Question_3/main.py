from datetime import date, datetime
from typing import List, Optional

from fastapi import FastAPI, Depends, Query, HTTPException
from pydantic import BaseModel, Field, validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from .settings import settings

app = FastAPI(title=settings.APP_NAME)


# ---------- Request / Response Schemas ----------

class TopRegionsQuery(BaseModel):
    start_date: Optional[date] = Field(None, description="Inclusive (YYYY-MM-DD)")
    end_date: Optional[date] = Field(None, description="Inclusive (YYYY-MM-DD)")
    categories: Optional[List[str]] = Field(None, description="Product categories to include")
    top_n: int = Field(settings.TOP_N, ge=1, le=100, description="How many regions to return (default 5)")

    @validator("end_date")
    def validate_range(cls, v, values):
        sd = values.get("start_date")
        if sd and v and v < sd:
            raise ValueError("end_date must be >= start_date")
        return v


class RegionAggregate(BaseModel):
    region: str
    total_sales: float
    orders_count: int


class TopRegionsResponse(BaseModel):
    generated_at: datetime
    query: TopRegionsQuery
    results: List[RegionAggregate]


# ---------- Endpoint ----------

@app.get("/analytics/top-regions", response_model=TopRegionsResponse, summary="Top N regions by total sales")
async def top_regions(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    category: Optional[List[str]] = Query(None, alias="category"),
    top_n: int = Query(settings.TOP_N, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """
    Returns the top N regions by SUM(total_amount) with optional filters:
    - start_date, end_date (inclusive)
    - category=cat1&category=cat2 (multi)
    """
    # Build dynamic WHERE safely with bind params
    where_clauses = []
    params = {}

    if start_date:
        where_clauses.append("sale_date >= :start_date")
        params["start_date"] = start_date
    if end_date:
        # Add 1 day to make end inclusive if your column is TIMESTAMP.
        # If it is DATE, you can keep it inclusive directly.
        where_clauses.append("sale_date < :end_exclusive")
        params["end_exclusive"] = datetime.combine(end_date, datetime.max.time())
    if category:
        where_clauses.append("category = ANY(:categories)")
        params["categories"] = category

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    # Large-scale friendly aggregation
    sql = text(f"""
        SELECT region,
               SUM(total_amount)::float8 AS total_sales,
               COUNT(*) AS orders_count
        FROM sales_data
        {where_sql}
        GROUP BY region
        ORDER BY total_sales DESC
        LIMIT :top_n
    """)
    params["top_n"] = top_n

    try:
        res = await session.execute(sql, params)
    except Exception as e:
        # Surface a clean message (the actual error remains in logs)
        raise HTTPException(status_code=500, detail="Query failed") from e

    rows = res.mappings().all()

    payload = TopRegionsResponse(
        generated_at=datetime.utcnow(),
        query=TopRegionsQuery(
            start_date=start_date,
            end_date=end_date,
            categories=category,
            top_n=top_n
        ),
        results=[RegionAggregate(**row) for row in rows],
    )
    return payload


@app.get("/health")
async def health():
    return {"ok": True}
