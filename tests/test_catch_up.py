"""Phase 0.5a - catch-up pipeline: no event may be lost because of the day of the week.

Background (docs/SPEC_poprawki_ksiegowe.md): run_daily used to match events on the
EXACT current date while the cron runs Mon-Fri only, so weekend events vanished -
13 customer invoices in October 2026 and 525 customer payments (74.3 mln NOK gross)
in the history. These tests pin the replacement:

* run_catch_up processes every calendar day in (watermark, today], once, in order;
* the watermark advances only after a day is fully processed;
* a cron that fires only on working days (with catch-up) yields EXACTLY the same orders
  and bank transactions as one that fires every single day;
* invoices keep their own date (weekends included); payments and supplier payments are
  booked on working days only, exactly once, for the stored gross amount.

Persistence is replaced by an in-memory FakeStore that mirrors the repository's query
windows, so the whole real generator stack runs (orders, hours, payroll, payments).
"""

import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_daily as run_daily_module  # noqa: E402

from norfingen.db import repository  # noqa: E402
from norfingen.generators.bank_transaction_generator import _incoming_payment_date  # noqa: E402
from norfingen.generators.money import pg_round2  # noqa: E402
from norfingen.generators.order_generator import generate_monthly_orders  # noqa: E402
from norfingen.generators.supplier_invoice_generator import generate_monthly_supplier_invoices  # noqa: E402
from norfingen.models.bank_transaction import BankTransactionType  # noqa: E402
from norfingen.models.order import OrderStatus  # noqa: E402
from norfingen.seed.roster import customer_by_id  # noqa: E402
from norfingen.seed.workdays import is_working_day, next_working_day  # noqa: E402


# ---------------------------------------------------------------- workdays

@pytest.mark.parametrize("day,expected", [
    (date(2026, 10, 30), date(2026, 10, 30)),  # Friday stays
    (date(2026, 10, 31), date(2026, 11, 2)),   # Saturday -> Monday
    (date(2026, 11, 1), date(2026, 11, 2)),    # Sunday -> Monday
    (date(2026, 11, 2), date(2026, 11, 2)),    # Monday stays
])
def test_next_working_day(day, expected):
    assert next_working_day(day) == expected


def test_next_working_day_is_always_a_working_day():
    day = date(2024, 1, 1)
    for _ in range(800):
        assert is_working_day(next_working_day(day))
        assert next_working_day(day) >= day
        day += timedelta(days=1)


# ---------------------------------------------------------------- catch-up control flow

def _control_flow_patches(watermark, hour_date=None):
    state = {"wm": watermark, "set": [], "processed": []}

    def fake_process_day(d, skip_setup=False):
        state["processed"].append(d)
        return {"orders": 1, "bank_transactions": 2, "hour_entries": 3, "salary": 0}

    def fake_set(d, key=None):
        state["set"].append(d)
        state["wm"] = d

    patches = dict(
        ensure_schema=MagicMock(),
        seed_reference_data=MagicMock(),
        get_watermark=MagicMock(side_effect=lambda: state["wm"]),
        set_watermark=MagicMock(side_effect=fake_set),
        latest_hour_entry_date=MagicMock(return_value=hour_date),
        process_day=MagicMock(side_effect=fake_process_day),
    )
    return state, patches


@pytest.mark.parametrize("gap_days", range(1, 11))  # every weekday alignment of "today" appears
def test_catch_up_processes_every_calendar_day_exactly_once_in_order(gap_days):
    today = date(2026, 11, 2)  # a Monday
    watermark = today - timedelta(days=gap_days)
    state, patches = _control_flow_patches(watermark)

    with patch.multiple(run_daily_module, **patches):
        totals = run_daily_module.run_catch_up(today=today)

    expected = [watermark + timedelta(days=i) for i in range(1, gap_days + 1)]
    assert state["processed"] == expected
    assert state["set"] == expected          # advanced day by day, after each day
    assert state["wm"] == today
    assert totals["days"] == gap_days and totals["orders"] == gap_days


def test_catch_up_includes_the_weekend_when_cron_skipped_it():
    friday, monday = date(2026, 10, 30), date(2026, 11, 2)
    state, patches = _control_flow_patches(friday)
    with patch.multiple(run_daily_module, **patches):
        run_daily_module.run_catch_up(today=monday)
    assert state["processed"] == [date(2026, 10, 31), date(2026, 11, 1), monday]  # Sat, Sun, Mon


def test_catch_up_is_a_no_op_when_watermark_is_today():
    today = date(2026, 11, 2)
    state, patches = _control_flow_patches(today)
    with patch.multiple(run_daily_module, **patches):
        totals = run_daily_module.run_catch_up(today=today)
    assert state["processed"] == [] and totals["days"] == 0


def test_failure_mid_period_leaves_watermark_at_last_completed_day():
    today = date(2026, 11, 2)
    state, patches = _control_flow_patches(date(2026, 10, 29))

    def boom_on_sunday(d, skip_setup=False):
        if d == date(2026, 11, 1):
            raise RuntimeError("db hiccup")
        state["processed"].append(d)
        return {}

    patches["process_day"] = MagicMock(side_effect=boom_on_sunday)
    with patch.multiple(run_daily_module, **patches):
        with pytest.raises(RuntimeError):
            run_daily_module.run_catch_up(today=today)

    assert state["wm"] == date(2026, 10, 31)   # Sunday not committed -> redone by the next run
    assert state["processed"] == [date(2026, 10, 30), date(2026, 10, 31)]


def test_first_run_without_watermark_starts_after_latest_hour_entry():
    today = date(2026, 11, 2)
    state, patches = _control_flow_patches(None, hour_date=date(2026, 10, 30))
    with patch.multiple(run_daily_module, **patches):
        run_daily_module.run_catch_up(today=today)
    assert state["processed"] == [date(2026, 10, 31), date(2026, 11, 1), today]


def test_first_run_with_empty_database_processes_only_today():
    today = date(2026, 11, 2)
    state, patches = _control_flow_patches(None, hour_date=None)
    with patch.multiple(run_daily_module, **patches):
        run_daily_module.run_catch_up(today=today)
    assert state["processed"] == [today]


def test_run_daily_with_explicit_date_processes_just_that_day():
    state, patches = _control_flow_patches(date(2026, 10, 1))
    with patch.multiple(run_daily_module, **patches):
        run_daily_module.run_daily(date(2024, 1, 6))
    assert state["processed"] == [date(2024, 1, 6)] and state["set"] == []  # backfill path never touches the watermark


# ---------------------------------------------------------------- full-stack: weekdays-only cron == every-day cron

class FakeStore:
    """In-memory stand-in for repository.py. Mirrors its query windows (invoice date within
    lookback of as_of; UNPAID supplier invoices with due date within lookback) and its
    idempotent unique keys, so it fails the same way the real thing would."""

    def __init__(self, seed_orders, seed_invoices, watermark):
        self.wm = watermark
        self.orders = {}          # (customer_id, order_date) -> Order (with id + storedGross)
        self.invoices = {}        # invoice id -> SupplierInvoice
        self.unpaid = set()
        self.payments = {}        # unique key -> BankTransaction
        self._next_id = 1
        for order in seed_orders:
            self.save_orders([order])
        for invoice in seed_invoices:
            self.invoices[self._next_id] = invoice.model_copy(update={"id": self._next_id})
            self.unpaid.add(self._next_id)
            self._next_id += 1

    # --- repository surface used by run_daily -------------------------------------------------
    def save_orders(self, orders):
        for order in orders:
            key = (order.customer.id, order.orderDate)
            if key in self.orders:
                continue  # ON CONFLICT DO NOTHING
            gross = round(sum(pg_round2(line.amountCurrency) for line in order.orderLines), 2)
            self.orders[key] = order.model_copy(update={"id": self._next_id, "storedGrossAmountCurrency": gross})
            self._next_id += 1

    def get_orders_for_payment_window(self, as_of, lookback_days=repository.ORDER_PAYMENT_LOOKBACK_DAYS):
        start = as_of - timedelta(days=lookback_days)
        return [o for o in self.orders.values() if start <= o.invoiceDate <= as_of]

    def get_unpaid_supplier_invoices(self, as_of, lookback_days=repository.MAX_PAYMENT_TERMS_DAYS + repository.PAYMENT_WEEKEND_SHIFT_MARGIN_DAYS):
        start = as_of - timedelta(days=lookback_days)
        return [i for iid, i in self.invoices.items() if iid in self.unpaid and start <= i.paymentDueDate <= as_of]

    def save_bank_transactions(self, pairs):
        for transaction, _voucher in pairs:
            key = (transaction.transaction_type, transaction.order_id, transaction.supplier_invoice_id,
                   transaction.salary_transaction_id, transaction.date)
            self.payments.setdefault(key, transaction)
            if transaction.transaction_type == BankTransactionType.OUTGOING and transaction.supplier_invoice_id:
                self.unpaid.discard(transaction.supplier_invoice_id)

    def save_salary(self, transaction, vouchers):
        return self._next_id

    def patches(self):
        return dict(
            ensure_schema=MagicMock(), seed_reference_data=MagicMock(),
            get_watermark=MagicMock(side_effect=lambda: self.wm),
            set_watermark=MagicMock(side_effect=lambda d, key=None: setattr(self, "wm", d)),
            latest_hour_entry_date=MagicMock(return_value=None),
            get_orders_for_payment_window=self.get_orders_for_payment_window,
            get_unpaid_supplier_invoices=self.get_unpaid_supplier_invoices,
            save_orders=self.save_orders, save_bank_transactions=self.save_bank_transactions,
            save_hour_entries=MagicMock(), save_salary=self.save_salary,
        )


WINDOW_START = date(2024, 2, 1)
WINDOW_END = date(2024, 4, 1)  # a Monday: both schedules end on a processed working day


def _seed():
    """What the monthly backfill left in the database: customer orders Sep 2023 - Jan 2024 (the window
    then creates Feb-Mar orders itself, through the daily path) and supplier invoices Nov 2023 - Mar 2024
    (supplier invoices come from the monthly mode only until phase 0.5b)."""
    orders, invoices = [], []
    for year, month in ((2023, 9), (2023, 10), (2023, 11), (2023, 12), (2024, 1)):
        orders += generate_monthly_orders(year, month)
    for year, month in ((2023, 11), (2023, 12), (2024, 1), (2024, 2), (2024, 3)):
        invoices += generate_monthly_supplier_invoices(year, month)
    return orders, invoices


def _run(schedule_days):
    orders, invoices = _seed()
    store = FakeStore(orders, invoices, watermark=WINDOW_START - timedelta(days=1))
    with patch.multiple(run_daily_module, **store.patches()):
        for day in schedule_days:
            run_daily_module.run_catch_up(today=day)
    return store


def _days(start, end, working_only):
    day, out = start, []
    while day <= end:
        if not working_only or is_working_day(day):
            out.append(day)
        day += timedelta(days=1)
    return out


@pytest.fixture(scope="module")
def every_day_store():
    return _run(_days(WINDOW_START, WINDOW_END, working_only=False))


@pytest.fixture(scope="module")
def weekdays_only_store():
    return _run(_days(WINDOW_START, WINDOW_END, working_only=True))


def test_weekdays_only_cron_equals_every_day_cron(every_day_store, weekdays_only_store):
    assert set(weekdays_only_store.orders) == set(every_day_store.orders)
    assert set(weekdays_only_store.payments) == set(every_day_store.payments)


def test_weekend_invoices_are_created_with_their_weekend_date(weekdays_only_store):
    weekend_orders = [o for (_, d), o in weekdays_only_store.orders.items()
                      if d >= WINDOW_START and not is_working_day(d)]
    assert weekend_orders, "no customer has invoice_day on a weekend in this window - pick another window"
    assert all(o.invoiceDate == o.orderDate for o in weekend_orders)


def test_every_payment_is_booked_on_a_working_day(weekdays_only_store):
    payments = [t for t in weekdays_only_store.payments.values() if t.date >= WINDOW_START]
    assert payments
    assert all(is_working_day(t.date) for t in payments)


def test_no_customer_payment_is_lost_or_duplicated(weekdays_only_store):
    """Every non-written-off invoice whose (shifted) payment date is inside the window has exactly
    one INCOMING payment, on that date, for the stored gross amount."""
    store = weekdays_only_store
    incoming = {}
    for t in store.payments.values():
        if t.transaction_type == BankTransactionType.INCOMING:
            incoming.setdefault(t.order_id, []).append(t)

    checked = 0
    for order in store.orders.values():
        if order.status == OrderStatus.WRITTEN_OFF:
            assert order.id not in incoming
            continue
        due = _incoming_payment_date(order, customer_by_id(order.customer.id).payment_terms)
        if not (WINDOW_START <= due <= WINDOW_END):
            continue
        checked += 1
        got = incoming.get(order.id, [])
        assert len(got) == 1, f"order {order.id} ({order.invoiceDate}, due {due}): {len(got)} payments"
        assert got[0].date == due
        assert got[0].amount == order.storedGrossAmountCurrency  # to the grosz, not recomputed
    assert checked > 40
    # the window really exercises the weekend shift (otherwise this test would prove nothing)
    shifted = [o for o in store.orders.values() if o.status != OrderStatus.WRITTEN_OFF
               and WINDOW_START <= _incoming_payment_date(o, customer_by_id(o.customer.id).payment_terms) <= WINDOW_END
               and not is_working_day(o.invoiceDate + timedelta(days=customer_by_id(o.customer.id).payment_terms)
                                      + (timedelta(days=repository.OVERDUE_PAYMENT_DELAY_DAYS) if o.status == OrderStatus.OVERDUE else timedelta(0)))]
    assert len(shifted) >= 5


def test_no_supplier_payment_is_lost_or_duplicated(weekdays_only_store):
    store = weekdays_only_store
    outgoing = {}
    for t in store.payments.values():
        if t.transaction_type == BankTransactionType.OUTGOING and t.supplier_invoice_id:
            outgoing.setdefault(t.supplier_invoice_id, []).append(t)

    checked = 0
    for iid, invoice in store.invoices.items():
        due = next_working_day(invoice.paymentDueDate)
        if not (WINDOW_START <= due <= WINDOW_END):
            continue
        checked += 1
        got = outgoing.get(iid, [])
        assert len(got) == 1, f"invoice {invoice.invoiceNumber} due {invoice.paymentDueDate}: {len(got)} payments"
        assert got[0].date == due
        assert iid not in store.unpaid
    assert checked > 8
