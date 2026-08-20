#!/usr/bin/env python3
"""Faza 7, Zadanie 6 — loguje faktycznie wylosowane zdarzenia (klienckie +
firmowe) w historii 2019 - dziś do CSV, żeby dało się je wypisać w
SESSION_HANDOFF.md bez ręcznego przeklejania z konsoli.

Czysto raportowe — nie zapisuje nic do Supabase, nie modyfikuje danych.
Deterministyczne (te same zdarzenia co realny backfill, bo korzysta z tych
samych funkcji generatorów).

Użycie:
    python scripts/log_life_events.py [--end YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from norfingen.generators.client_events import customer_event_state_asof  # noqa: E402
from norfingen.generators.company_events import (  # noqa: E402
    equipment_investment_trigger,
    roll_company_events,
    supplier_cost_multiplier,
    unprofitable_quarter_cost_spike,
)
from norfingen.seed.roster import CUSTOMERS, SUPPLIERS  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "faza7_life_events_log.csv"


def collect_client_events(end_date: date) -> list[dict]:
    rows = []
    for customer in CUSTOMERS:
        if customer.order_pattern not in ("A", "B", "C"):
            continue  # K06 wykluczony — zob. client_events.py
        year, month = customer.onboarding_date.year, customer.onboarding_date.month
        while (year, month) <= (end_date.year, end_date.month):
            state = customer_event_state_asof(customer.number, year, month)
            if state.triggered_this_month:
                rows.append({
                    "scope": "client",
                    "code": state.triggered_this_month,
                    "year": year,
                    "month": month,
                    "customer_number": customer.number,
                    "customer_name": customer.name,
                    "segment": customer.segment,
                    "detail": _client_event_detail(state),
                })
            year, month = (year, month + 1) if month < 12 else (year + 1, 1)
    return rows


def _client_event_detail(state) -> str:
    if state.triggered_this_month == "OFFER_EXPANSION":
        return f"added={state.added_service}"
    if state.triggered_this_month == "OFFER_REDUCTION":
        return f"removed={state.removed_service}"
    if state.triggered_this_month == "TEMPORARY_HARDSHIP":
        return f"until={state.hardship_active_until} multiplier={state.hardship_ticket_multiplier:.3f}"
    if state.triggered_this_month == "BANKRUPTCY":
        return "churned"
    if state.triggered_this_month == "ONE_OFF_LARGE_PROJECT":
        return "large S04 order"
    return ""


def _company_event_detail(code: str, year: int, month: int) -> str:
    if code == "EQUIPMENT_INVESTMENT":
        amount = equipment_investment_trigger(year, month)
        return f"amount={amount:,.0f} NOK"
    if code == "UNPROFITABLE_QUARTER":
        spike = unprofitable_quarter_cost_spike(year, month)
        return f"cost_spike={spike:,.0f} NOK"
    if code == "SUPPLIER_RENEGOTIATION":
        prev_year, prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
        before = {s.number: supplier_cost_multiplier(s.number, prev_year, prev_month) for s in SUPPLIERS}
        after = {s.number: supplier_cost_multiplier(s.number, year, month) for s in SUPPLIERS}
        changed = [s for s in before if before[s] != after[s]]
        if changed:
            supplier = changed[0]
            pct = (after[supplier] / before[supplier] - 1) * 100
            return f"supplier={supplier} change={pct:+.1f}%"
    return ""


def collect_company_events(end_date: date) -> list[dict]:
    """Filtrowane do (rok, miesiąc) <= end_date — roll_company_events(year)
    losuje zdarzenia dla CAŁEGO roku naraz (Zadanie 3b), więc bez tego
    filtra log pokazywałby zdarzenia z miesięcy, które backfill jeszcze
    nie objął (np. wrzesień bieżącego, niedokończonego roku)."""
    rows = []
    for year in range(2019, end_date.year + 1):
        for ev in roll_company_events(year):
            if (ev["year"], ev["month"]) > (end_date.year, end_date.month):
                continue
            rows.append({
                "scope": "company",
                "code": ev["code"],
                "year": ev["year"],
                "month": ev["month"],
                "customer_number": "",
                "customer_name": "",
                "segment": "",
                "detail": _company_event_detail(ev["code"], ev["year"], ev["month"]),
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()

    rows = collect_client_events(args.end) + collect_company_events(args.end)
    rows.sort(key=lambda r: (r["year"], r["month"], r["scope"], r["customer_number"]))

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["scope", "code", "year", "month", "customer_number", "customer_name", "segment", "detail"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} zdarzeń zapisanych do {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
