#!/usr/bin/env python3
"""Generuje dane NorFinGen i zapisuje je do Supabase.

CLI:
    python run_daily.py          # nadrabia WSZYSTKIE dni od ostatnio przetworzonego do dziś

Importowalny jako funkcja:
    from run_daily import run_daily
    run_daily()                  # catch-up (watermark, dziś]
    run_daily(date(2024, 1, 3))  # dokładnie jeden dzień (backfill, testy)

Faza 0.5a — catch-up zamiast dopasowania do dokładnej daty "dziś". Wcześniej
przebieg dzienny przetwarzał tylko zdarzenia o dacie równej dzisiejszej, a cron
(`daily.yml`) działa tylko pon.-pt., więc zdarzenia z soboty/niedzieli ginęły
na zawsze: faktury klientów z `invoice_day` w weekend (13 faktur w październiku
2026), wpłaty klientów z terminem w weekend (525 faktur, 74,3 mln NOK brutto) i
płatności dla dostawców. Teraz każdy przebieg bierze wszystkie dni
kalendarzowe z okresu (watermark, dziś] (tabela `generation_state`) i przesuwa
watermark dopiero po pełnym zatwierdzeniu dnia. Pominięty dzień (awaria
crona, weekend, maszyna uśpiona) jest nadrabiany przy następnym przebiegu.

Zasady dat:
  - faktury sprzedaży zachowują swoją datę, także weekendową (jak w backfillu),
  - wpłaty klientów i płatności dostawców wypadające w weekend księgowane są
    w następnym dniu roboczym (seed.workdays.next_working_day),
  - kwota wpłaty = SUM(order_lines.amount_currency) z bazy, nie przeliczenie.

Dla każdego dnia kalendarzowego (process_day) — TEN SAM kod dla historii
(`run_backfill.py`) i dla dnia bieżącego (cron):
0. Kapitał zakładowy (jednorazowo, 2019-01-02)
1. Zamówienia klientów datowane tego dnia (day_events.orders_dated: zwykłe faktury,
   K06, extra consulting, duży projekt, skutki zdarzeń klienta) wraz z voucherem
   sprzedaży OUTGOING_INVOICE (Wn 1500 / Ma 3000 / Ma 2700, faza 3)
2. Faktury zakupu datowane tego dnia + ich vouchery; COGS i koszty operacyjne
   datowane tego dnia (day_events); naliczenie COGS dostaje własne zobowiązanie
   (cogs_payables, faza 4), żeby dało się je zapłacić
3. Płatności bankowe z terminem (po przesunięciu na dzień roboczy) przypadającym
   tego dnia — wpłaty klientów, płatności dostawców i zobowiązań COGS; po
   zaksięgowaniu faktura zakupu / zobowiązanie COGS zmienia status UNPAID -> PAID
   (jedyna droga do PAID)
4. Godziny pracy konsultantów, jeśli to dzień roboczy (generate_daily_hours)
5. Lista płac, jeśli to ostatni dzień roboczy miesiąca (generate_monthly_salary)

Faza 0.5b — jeden potok. Wcześniej historię budował tryb miesięczny, a cron miał
własną, uboższą ścieżkę (bez faktur zakupu, COGS, kosztów operacyjnych i skutków
zdarzeń), stąd zerowe koszty w październiku 2026. Teraz miesiąc jest generowany w
CAŁOŚCI tymi samymi funkcjami `generate_monthly_*` i dzień bierze swój wycinek
(zob. generators/day_events.py).

Idempotentny: ON CONFLICT DO NOTHING na naturalnych kluczach biznesowych we
wszystkich tabelach — powtórne przetworzenie tego samego dnia nie tworzy
duplikatów.
"""

from __future__ import annotations

import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from norfingen.db.repository import (  # noqa: E402
    ensure_schema,
    get_orders_for_payment_window,
    get_orders_to_write_off,
    get_unpaid_cogs_payables,
    get_unpaid_supplier_invoices,
    get_unpaid_vat_settlements,
    get_vat_period_totals,
    get_watermark,
    latest_hour_entry_date,
    save_all,
    save_bank_transactions,
    save_cogs_accrual,
    save_write_off,
    save_hour_entries,
    save_orders,
    save_salary,
    save_vat_settlement,
    seed_reference_data,
    set_watermark,
)
from norfingen.generators.backfill import FOUNDING_CAPITAL_DATE, founding_capital_voucher  # noqa: E402
from norfingen.generators.owner_loan import loan_drawdown_voucher, loan_service_voucher  # noqa: E402
from norfingen.generators.write_off import build_write_off_voucher  # noqa: E402
from norfingen.generators.bank_transaction_generator import (  # noqa: E402
    generate_daily_bank_transactions,
    generate_payroll_bank_transaction,
)
from norfingen.generators.hours_generator import generate_daily_hours  # noqa: E402
from norfingen.generators.opex_generator import cogs_payable_for  # noqa: E402
from norfingen.generators.day_events import (  # noqa: E402
    operating_vouchers_dated,
    orders_dated,
    supplier_invoices_dated,
)
from norfingen.generators.sales_voucher import build_sales_voucher  # noqa: E402
from norfingen.generators.vat_settlement import build_vat_settlement, term_bounds, term_ending_on  # noqa: E402
from norfingen.generators.salary_generator import generate_monthly_salary  # noqa: E402
from norfingen.generators.supplier_invoice_generator import build_voucher_for_invoice  # noqa: E402
from norfingen.seed.payroll import active_employees, last_working_day, should_generate_monthly_salary  # noqa: E402
from norfingen.seed.roster import numeric_id, supplier_by_number  # noqa: E402

logger = logging.getLogger("run_daily")


def process_day(target_date: date, skip_setup: bool = False) -> dict:
    """Przetwarza wszystkie zdarzenia JEDNEGO dnia kalendarzowego (także
    soboty i niedziele — wtedy powstają tylko faktury klientów z invoice_day
    w weekend; wpłaty i płatności są wcześniej przesunięte na dzień roboczy,
    godziny i płace mają własne warunki dnia roboczego).

    skip_setup=True pomija ensure_schema()/seed_reference_data() — używane
    przez pętle (catch-up, run_backfill.py::run_backfill_daily()), które
    wykonują setup raz na starcie; bez tego każde z ~2000 wywołań
    powtarzałoby ~50 idempotentnych, ale niepotrzebnych round-tripów."""

    # Faza 5a — generator NIGDY nie tworzy rekordów z datą późniejszą niż
    # dzisiaj; bezpiecznik na wypadek wywołania run_daily() z przyszłą datą
    # (np. pomyłka wywołującego kodu, nie tylko backfill).
    if target_date > date.today():
        logger.warning("run_daily: target_date %s jest w przyszłości — pomijam.", target_date)
        return {
            "orders": 0, "supplier_invoices": 0, "operating_costs": 0,
            "bank_transactions": 0, "hour_entries": 0, "salary": 0, "skipped": True,
        }

    year, month, day = target_date.year, target_date.month, target_date.day

    if not skip_setup:
        ensure_schema()
        seed_reference_data()

    stats = {
        "orders": 0, "supplier_invoices": 0, "operating_costs": 0,
        "bank_transactions": 0, "hour_entries": 0, "salary": 0,
    }

    # 0. Kapitał zakładowy otwiera księgi (jednorazowy voucher MANUAL).
    if target_date == FOUNDING_CAPITAL_DATE:
        save_all(founding_capital_voucher())
        save_all(loan_drawdown_voucher())  # audit phase 3: the owner's start-up loan arrives with the capital

    # 1. Zamówienia klientów datowane dzisiaj (także weekendowe: faktura zachowuje swoją datę).
    orders = orders_dated(target_date)
    if orders:
        save_orders(orders)
        # ... and its sales voucher: Dr 1500 / Cr 3000 / Cr 2700 on the invoice date (phase 3).
        for order in orders:
            save_all(build_sales_voucher(order))
        stats["orders"] = len(orders)

    # 2. Faktury zakupu (+ voucher INCOMING_INVOICE) i koszty operacyjne/COGS datowane dzisiaj.
    #    Faktura powstaje jako UNPAID; PAID dopiero po zaksięgowaniu płatności (krok 3).
    for invoice in supplier_invoices_dated(target_date):
        save_all(invoice)
        save_all(build_voucher_for_invoice(invoice, supplier_by_number(invoice.invoiceNumber.split("-")[0])))
        stats["supplier_invoices"] += 1
    for voucher in operating_vouchers_dated(target_date):
        payable = cogs_payable_for(voucher)
        if payable is not None:
            save_cogs_accrual(voucher, payable)  # COGS pass-through: the liability gets its payable (phase 4)
        else:
            save_all(voucher)
        stats["operating_costs"] += 1

    # 2a. Spisanie należności, które nie zostaną zapłacone (audyt, faza 4): 120 dni po terminie płatności faktury.
    #     PRZED krokiem 2b: jeśli to ostatni dzień terminu VAT, korekta 2700 musi być już w księdze, gdy liczone są sumy.
    for order in get_orders_to_write_off(target_date):
        voucher = build_write_off_voucher(order)
        if voucher is not None:
            save_write_off(voucher, order.id)
            stats["write_offs"] = stats.get("write_offs", 0) + 1

    # 2b. Last day of a VAT term: the balances of 2700 / 2710 move to 2740 (phase 5). After steps 1-2, so that the
    #     invoices of the very last day of the term are in the ledger when the totals are read.
    term = term_ending_on(target_date)
    if term is not None:
        start, end = term_bounds(*term)
        built = build_vat_settlement(*term, *get_vat_period_totals(start, end))
        if built is not None:
            save_vat_settlement(*built)

    # 3. Płatności bankowe — potrzebujemy zamówień/faktur z bazy (nie tylko
    #    dzisiejszych), żeby dopasować payment_terms/payment_due_date == dzisiaj
    pending_orders = get_orders_for_payment_window(target_date)
    pending_invoices = get_unpaid_supplier_invoices(target_date)
    pending_cogs = get_unpaid_cogs_payables(target_date)
    pending_vat = get_unpaid_vat_settlements(target_date)
    bank_txns = generate_daily_bank_transactions(
        year, month, day, pending_orders, pending_invoices, pending_cogs, pending_vat,
    )
    if bank_txns:
        save_bank_transactions(bank_txns)
        stats["bank_transactions"] = len(bank_txns)

    # 4. Godziny pracy konsultantów (generate_daily_hours sama filtruje dni robocze)
    active_ids = [numeric_id(e.number) for e in active_employees(target_date)]
    hour_entries = generate_daily_hours(year, month, day, active_ids)
    if hour_entries:
        save_hour_entries(hour_entries)
        stats["hour_entries"] = len(hour_entries)

    # 5. Lista płac — tylko w ostatni dzień roboczy miesiąca, i tylko jeśli
    # ten dzień faktycznie już minął (should_generate_monthly_salary — Faza 5a).
    if target_date == last_working_day(year, month) and should_generate_monthly_salary(year, month):
        salary_txn, vouchers = generate_monthly_salary(year, month)
        transaction_id = save_salary(salary_txn, vouchers)
        stats["salary"] = 1

        # Krok 2 — naprawa: payroll wypłacony tego samego dnia = odpływ z
        # banku (dawniej brakowało tego kroku w ogóle, zob.
        # bank_transaction_generator.generate_payroll_bank_transaction).
        # transaction_id to prawdziwe ID z bazy (save_salary je zwraca) —
        # potrzebne do FK salary_transaction_id.
        salary_txn.id = transaction_id
        payroll_payment = generate_payroll_bank_transaction(salary_txn, vouchers)
        if payroll_payment is not None:
            save_bank_transactions([payroll_payment])
            stats["bank_transactions"] += 1

    # 6. Obsługa pożyczki od właściciela (audyt, faza 3): odsetki (+ rata od 2021) w ostatnim dniu roboczym miesiąca.
    loan_voucher = loan_service_voucher(target_date)
    if loan_voucher is not None:
        save_all(loan_voucher)

    logger.info("run_daily %s: %s", target_date.isoformat(), stats)
    return stats


def run_catch_up(today: Optional[date] = None, skip_setup: bool = False) -> dict:
    """Przetwarza każdy dzień kalendarzowy z okresu (watermark, today].

    Watermark (generation_state) przesuwamy dopiero PO zatwierdzeniu całego
    dnia — jeśli przebieg padnie w połowie dnia, następny zacznie od tego dnia
    od nowa, co jest bezpieczne dzięki idempotencji zapisów. Gdy watermark nie
    istnieje (baza sprzed fazy 0.5a), startujemy od ostatniego dnia z
    hour_entries (godziny powstają w każdy dzień roboczy), a gdyby i tego nie
    było — od wczoraj."""
    if today is None:
        today = date.today()
    if not skip_setup:
        ensure_schema()
        seed_reference_data()

    watermark = get_watermark()
    if watermark is None:
        watermark = latest_hour_entry_date(today) or (today - timedelta(days=1))
        logger.warning("run_daily: brak watermarku - startuję od %s (ostatnie hour_entries).", watermark)

    totals = {
        "orders": 0, "supplier_invoices": 0, "operating_costs": 0,
        "bank_transactions": 0, "hour_entries": 0, "salary": 0, "days": 0,
    }
    day = watermark + timedelta(days=1)
    while day <= today:
        stats = process_day(day, skip_setup=True)
        set_watermark(day)
        for key in ("orders", "supplier_invoices", "operating_costs", "bank_transactions", "hour_entries", "salary"):
            totals[key] += stats.get(key, 0)
        totals["days"] += 1
        day += timedelta(days=1)

    logger.info("run_daily catch-up (%s, %s]: %s", watermark.isoformat(), today.isoformat(), totals)
    return totals


def run_daily(target_date: Optional[date] = None, skip_setup: bool = False) -> dict:
    """Bez argumentu: catch-up od ostatnio przetworzonego dnia do dziś (tryb
    crona). Z `target_date`: dokładnie ten jeden dzień (backfill, testy)."""
    if target_date is None:
        return run_catch_up(skip_setup=skip_setup)
    return process_day(target_date, skip_setup=skip_setup)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_daily()


if __name__ == "__main__":
    main()
