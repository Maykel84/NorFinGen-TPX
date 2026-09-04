"""Klienci — lista filtrowalna po segmencie/aktywności, i pojedynczy klient."""

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import verify_api_key
from api.db import data_pool
from api.models import Customer, Page
from api.pagination import pagination_params

router = APIRouter(prefix="/customers", tags=["customers"])

_VALID_SEGMENTS = {"Enterprise", "Mid-market", "SMB"}


def _row_to_customer(row) -> Customer:
    d = dict(row)
    d["active"] = d["churn_date"] is None
    return Customer(**d)


@router.get("", response_model=Page[Customer])
async def list_customers(
    segment: str | None = Query(default=None, description="Enterprise / Mid-market / SMB"),
    active: bool | None = Query(default=None, description="true = bez churn_date, false = z churn_date"),
    pagination: tuple[int, int] = Depends(pagination_params),
    _owner: str = Depends(verify_api_key),
) -> Page[Customer]:
    if segment is not None and segment not in _VALID_SEGMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"'segment' musi być jednym z {sorted(_VALID_SEGMENTS)}, dostano '{segment}'.",
        )
    limit, offset = pagination

    conditions = []
    params: list = []

    def add_condition(sql: str, value) -> None:
        params.append(value)
        conditions.append(sql.format(n=len(params)))

    if segment is not None:
        add_condition("segment = ${n}", segment)
    if active is True:
        conditions.append("churn_date IS NULL")
    elif active is False:
        conditions.append("churn_date IS NOT NULL")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    pool = data_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval(f"SELECT COUNT(*) FROM customers {where_clause}", *params)
        rows = await conn.fetch(
            f"""
            SELECT id, customer_number, name, city, segment, onboarding_date,
                   churn_date, nace_code, nace_name, postal_code
            FROM customers
            {where_clause}
            ORDER BY id
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """,
            *params,
            limit,
            offset,
        )
    return Page(items=[_row_to_customer(r) for r in rows], limit=limit, offset=offset, total=total)


@router.get("/{customer_number}", response_model=Customer)
async def get_customer(customer_number: str, _owner: str = Depends(verify_api_key)) -> Customer:
    pool = data_pool()
    row = await pool.fetchrow(
        """
        SELECT id, customer_number, name, city, segment, onboarding_date,
               churn_date, nace_code, nace_name, postal_code
        FROM customers
        WHERE customer_number = $1
        """,
        customer_number,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Klient '{customer_number}' nie znaleziony.")
    return _row_to_customer(row)
