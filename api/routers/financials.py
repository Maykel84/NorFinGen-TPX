"""P&L (rachunek zysków i strat) oraz zamówienia sprzedażowe.

Czyta wyłącznie z widoków BI istniejących już w bazie (`v_pl_monthly`,
`v_sales_flat` - zob. docs/DATA_DICTIONARY.md, sekcja "Widoki BI"), nie z
tabel źródłowych bezpośrednio - te widoki są już wystawione roli `analyst`
(`demo_reader` ją dziedziczy), więc nie trzeba tu żadnej dodatkowej logiki
JOIN-ów ani żadnych nowych uprawnień.
"""

import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import verify_api_key
from api.db import data_pool
from api.models import OrderSummary, Page, PLMonthly, PLTrailing, PLYearly
from api.pagination import pagination_params

router = APIRouter(tags=["financials"])

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _validate_month(value: str, param_name: str) -> str:
    """Waliduje 'YYYY-MM' - `v_pl_monthly`/`v_headcount_monthly`.`month` jest TEXT
    w tym dokładnym formacie (`to_char(..., 'YYYY-MM')`), nie DATE - zob.
    docs/DATA_DICTIONARY.md, "Widoki BI". Porównanie zakresu działa poprawnie
    jako porównanie leksykograficzne stringów w tym formacie (zero-padded)."""
    if not _MONTH_RE.match(value):
        raise HTTPException(
            status_code=400, detail=f"'{param_name}' musi być w formacie YYYY-MM, dostano '{value}'."
        )
    return value


@router.get("/pl/monthly", response_model=list[PLMonthly])
async def pl_monthly(
    from_: str = Query(alias="from", description="Miesiąc początkowy, format YYYY-MM"),
    to: str = Query(description="Miesiąc końcowy (włącznie), format YYYY-MM"),
    _owner: str = Depends(verify_api_key),
) -> list[PLMonthly]:
    """Miesięczny P&L (przychód, koszty pracy, koszty operacyjne, COGS, wynik operacyjny)."""
    month_from = _validate_month(from_, "from")
    month_to = _validate_month(to, "to")
    if month_from > month_to:
        raise HTTPException(status_code=400, detail="'from' musi być <= 'to'.")

    pool = data_pool()
    rows = await pool.fetch(
        """
        SELECT month, revenue, labor_cost, operating_cost, cogs, operating_result, is_partial,
               depreciation, ebitda, financial_result, tax, net_result
        FROM v_pl_monthly
        WHERE month >= $1 AND month <= $2
        ORDER BY month
        """,
        month_from,
        month_to,
    )
    return [PLMonthly(**dict(r)) for r in rows]


@router.get("/pl/yearly", response_model=list[PLYearly])
async def pl_yearly(_owner: str = Depends(verify_api_key)) -> list[PLYearly]:
    """P&L zagregowany rocznie (suma PEŁNYCH miesięcy `v_pl_monthly` per rok).

    Bieżący, niezakończony miesiąc (`is_partial`) jest pominięty: płace i COGS księgują się na koniec miesiąca, więc
    jego wynik jest zawyżony. Surowe wiersze (z flagą) zwraca `/pl/monthly`."""
    pool = data_pool()
    rows = await pool.fetch(
        """
        SELECT
            LEFT(month, 4)::int AS year,
            COALESCE(SUM(revenue), 0) AS revenue,
            COALESCE(SUM(labor_cost), 0) AS labor_cost,
            COALESCE(SUM(operating_cost), 0) AS operating_cost,
            COALESCE(SUM(cogs), 0) AS cogs,
            COALESCE(SUM(operating_result), 0) AS operating_result,
            COUNT(*)::int AS months_included
        FROM v_pl_monthly
        WHERE NOT is_partial
        GROUP BY 1
        ORDER BY 1
        """
    )
    result = []
    for r in rows:
        d = dict(r)
        d["margin_pct"] = round(d["operating_result"] / d["revenue"] * 100, 2) if d["revenue"] else None
        result.append(PLYearly(**d))
    return result


@router.get("/pl/trailing-12m", response_model=PLTrailing)
async def pl_trailing_12m(_owner: str = Depends(verify_api_key)) -> PLTrailing:
    """P&L z ostatnich 12 PEŁNYCH miesięcy (bez bieżącego, niezakończonego)."""
    pool = data_pool()
    rows = await pool.fetch(
        """
        SELECT month, revenue, labor_cost, operating_cost, cogs, operating_result
        FROM v_pl_monthly
        WHERE NOT is_partial
        ORDER BY month DESC
        LIMIT 12
        """
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Brak zakończonych miesięcy.")
    months = sorted(r["month"] for r in rows)
    total = lambda col: float(sum(r[col] or 0 for r in rows))  # noqa: E731
    revenue, result = total("revenue"), total("operating_result")
    return PLTrailing(
        period_from=months[0],
        period_to=months[-1],
        months=len(rows),
        revenue=revenue,
        labor_cost=total("labor_cost"),
        operating_cost=total("operating_cost"),
        cogs=total("cogs"),
        operating_result=result,
        margin_pct=round(result / revenue * 100, 2) if revenue else None,
    )


@router.get("/orders", response_model=Page[OrderSummary])
async def list_orders(
    from_: date = Query(alias="from", description="Data zamówienia od (włącznie)"),
    to: date = Query(description="Data zamówienia do (włącznie)"),
    pagination: tuple[int, int] = Depends(pagination_params),
    _owner: str = Depends(verify_api_key),
) -> Page[OrderSummary]:
    """Zamówienia sprzedażowe w zakresie dat, zagregowane per zamówienie
    (`v_sales_flat` jest na poziomie linii faktury - tu sumujemy do poziomu
    zamówienia)."""
    if from_ > to:
        raise HTTPException(status_code=400, detail="'from' musi być <= 'to'.")
    limit, offset = pagination

    pool = data_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT order_id) FROM v_sales_flat
            WHERE order_date >= $1 AND order_date <= $2
            """,
            from_,
            to,
        )
        rows = await conn.fetch(
            """
            SELECT
                order_id, customer_id, customer_number, customer_name,
                order_date, invoice_date, segment,
                SUM(amount_excluding_vat_currency) AS amount_excluding_vat,
                SUM(amount_including_vat_currency) AS amount_including_vat
            FROM v_sales_flat
            WHERE order_date >= $1 AND order_date <= $2
            GROUP BY order_id, customer_id, customer_number, customer_name, order_date, invoice_date, segment
            ORDER BY order_date, order_id
            LIMIT $3 OFFSET $4
            """,
            from_,
            to,
            limit,
            offset,
        )
    return Page(items=[OrderSummary(**dict(r)) for r in rows], limit=limit, offset=offset, total=total)
