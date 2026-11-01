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
  booked on working days only, exactly once, for the stored gross amount;
* (0.5b) supplier invoices, COGS and operating costs now come out of the same pipeline,
  and a supplier invoice becomes PAID only through its booked payment.

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
from norfingen.generators.voucher import Voucher  # noqa: E402
from norfingen.generators.opex_generator import cogs_payable_for  # noqa: E402
from norfingen.models.bank_transaction import BankTransactionType  # noqa: E402
from norfingen.models.cogs_payable import CogsPayableStatus  # noqa: E402
from norfingen.models.vat_settlement import VatSettlementStatus  # noqa: E402
from norfingen.models.order import OrderStatus  # noqa: E402
from norfingen.models.supplier_invoice import SupplierInvoice  # noqa: E402
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
        self.vouchers = {}        # (date, description) -> Voucher   (ON CONFLICT (date, description) DO NOTHING)
        self.cogs = {}            # payable id -> CogsPayable (UNPAID until its payment is booked)
        self.vat = {}             # (year, term) -> VatSettlement (UNPAID until its payment is booked)
        self.vat_vouchers = {}    # (year, term) -> settlement Voucher
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

    def save_all(self, obj):
        if isinstance(obj, SupplierInvoice):
            if any(i.invoiceNumber == obj.invoiceNumber for i in self.invoices.values()):
                return  # ON CONFLICT (invoice_number) DO NOTHING
            self.invoices[self._next_id] = obj.model_copy(update={"id": self._next_id})
            self.unpaid.add(self._next_id)  # created UNPAID, whatever the generator said
            self._next_id += 1
        elif isinstance(obj, Voucher):
            self.vouchers.setdefault((obj.date, obj.description), obj)
        else:
            raise TypeError(type(obj))

    def save_cogs_accrual(self, voucher, payable):
        if (voucher.date, voucher.description) in self.vouchers:
            return  # ON CONFLICT DO NOTHING
        self.vouchers[(voucher.date, voucher.description)] = voucher
        self.cogs[self._next_id] = payable.model_copy(update={"id": self._next_id})
        self._next_id += 1

    def get_unpaid_cogs_payables(self, as_of, lookback_days=None):
        lookback_days = lookback_days or (repository.MAX_PAYMENT_TERMS_DAYS + repository.PAYMENT_WEEKEND_SHIFT_MARGIN_DAYS)
        start = as_of - timedelta(days=lookback_days)
        return [p for p in self.cogs.values()
                if p.status == CogsPayableStatus.UNPAID and start <= p.payment_due_date <= as_of]

    def get_vat_period_totals(self, start, end):
        out = inp = 0.0
        for v in self.vouchers.values():           # settlement vouchers live elsewhere (self.vat_vouchers)
            if start <= v.date <= end:
                for p in v.postings:
                    if p.account.number == 2700:
                        out -= p.amount
                    elif p.account.number == 2710:
                        inp += p.amount
        return round(out, 2), round(inp, 2)

    def save_vat_settlement(self, voucher, settlement):
        key = (settlement.period_year, settlement.term)
        if key in self.vat:
            return  # ON CONFLICT DO NOTHING
        self.vat_vouchers[key] = voucher
        self.vat[key] = settlement.model_copy(update={"id": self._next_id})
        self._next_id += 1

    def get_unpaid_vat_settlements(self, as_of, lookback_days=14):
        start = as_of - timedelta(days=lookback_days)
        return [s for s in self.vat.values() if s.status == VatSettlementStatus.UNPAID and start <= s.payment_date <= as_of]

    def save_bank_transactions(self, pairs):
        for transaction, _voucher in pairs:
            key = (transaction.transaction_type, transaction.order_id, transaction.supplier_invoice_id,
                   transaction.salary_transaction_id, transaction.cogs_payable_id, transaction.vat_settlement_id,
                   transaction.date)
            self.payments.setdefault(key, transaction)
            if transaction.transaction_type == BankTransactionType.OUTGOING and transaction.supplier_invoice_id:
                self.unpaid.discard(transaction.supplier_invoice_id)
            if transaction.vat_settlement_id:
                for k, s in self.vat.items():
                    if s.id == transaction.vat_settlement_id:
                        self.vat[k] = s.model_copy(update={"status": VatSettlementStatus.PAID})
            if transaction.transaction_type == BankTransactionType.OUTGOING and transaction.cogs_payable_id:
                payable = self.cogs[transaction.cogs_payable_id]
                self.cogs[transaction.cogs_payable_id] = payable.model_copy(update={"status": CogsPayableStatus.PAID})

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
            get_unpaid_cogs_payables=self.get_unpaid_cogs_payables, save_cogs_accrual=self.save_cogs_accrual,
            get_vat_period_totals=self.get_vat_period_totals, save_vat_settlement=self.save_vat_settlement,
            get_unpaid_vat_settlements=self.get_unpaid_vat_settlements,
            save_orders=self.save_orders, save_all=self.save_all, save_bank_transactions=self.save_bank_transactions,
            save_hour_entries=MagicMock(), save_salary=self.save_salary,
        )


WINDOW_START = date(2024, 2, 1)
WINDOW_END = date(2024, 4, 1)  # a Monday: both schedules end on a processed working day


def _seed():
    """What the database already holds before the window: customer orders Sep 2023 - Jan 2024 and
    supplier invoices Nov 2023 - Jan 2024. The window itself (Feb - Mar 2024) is produced entirely by
    the pipeline: orders, supplier invoices + vouchers, operating costs and COGS."""
    orders, invoices = [], []
    for year, month in ((2023, 9), (2023, 10), (2023, 11), (2023, 12), (2024, 1)):
        orders += generate_monthly_orders(year, month)
    for year, month in ((2023, 11), (2023, 12), (2024, 1)):
        invoices += generate_monthly_supplier_invoices(year, month)
    return orders, invoices


def _run(schedule_days, start=None):
    start = start or WINDOW_START
    orders, invoices = _seed()
    store = FakeStore(orders, invoices, watermark=start - timedelta(days=1))
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
    assert {i.invoiceNumber for i in weekdays_only_store.invoices.values()} == {
        i.invoiceNumber for i in every_day_store.invoices.values()}
    assert set(weekdays_only_store.vouchers) == set(every_day_store.vouchers)
    assert {(p.accrual_date, p.account_number) for p in weekdays_only_store.cogs.values()} == {
        (p.accrual_date, p.account_number) for p in every_day_store.cogs.values()}
    paid = lambda store: sorted((p.accrual_date, p.account_number) for p in store.cogs.values() if p.status == CogsPayableStatus.PAID)
    assert paid(weekdays_only_store) == paid(every_day_store)
    assert weekdays_only_store.unpaid and len(weekdays_only_store.unpaid) == len(every_day_store.unpaid)


def test_pipeline_produces_exactly_the_monthly_generators_output_for_the_window(weekdays_only_store):
    """One pipeline for history and the current day: Feb-Mar 2024 built day by day equals the whole-month
    generators (orders incl. K06/extra consulting, supplier invoices, operating costs and COGS)."""
    store = weekdays_only_store
    window = [(2024, 2), (2024, 3), (2024, 4)]  # the window ends on Monday 2024-04-01
    expected_orders = {(o.customer.id, o.orderDate) for y, m in window for o in generate_monthly_orders(y, m)
                       if o.orderDate <= WINDOW_END}
    assert {k for k in store.orders if k[1] >= WINDOW_START} == expected_orders

    expected_invoices = {i.invoiceNumber for y, m in window for i in generate_monthly_supplier_invoices(y, m)
                         if i.invoiceDate <= WINDOW_END}
    got_invoices = {i.invoiceNumber for i in store.invoices.values() if i.invoiceDate >= WINDOW_START}
    assert got_invoices == expected_invoices

    cost_vouchers = {k for k, v in store.vouchers.items()
                     if k[0] >= WINDOW_START and v.voucherType.value == "OPERATING_COST"}
    assert len(cost_vouchers) >= 2 * 4  # canteen, representation, transport, S01 + S02 COGS, 3 first-of-months


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


def test_no_cogs_payment_is_lost_or_duplicated(weekdays_only_store):
    """Phase 4: every COGS accrual whose (shifted) due date is inside the window has exactly one payment, on that date, for the
    accrued amount, and its payable is PAID - a weekday-only cron with catch-up loses none (the weekend-due ones included)."""
    store = weekdays_only_store
    payments = {}
    for t in store.payments.values():
        if t.transaction_type == BankTransactionType.OUTGOING and t.cogs_payable_id:
            payments.setdefault(t.cogs_payable_id, []).append(t)

    checked = shifted = 0
    for pid, payable in store.cogs.items():
        due = next_working_day(payable.payment_due_date)
        if not (WINDOW_START <= due <= WINDOW_END):
            continue
        checked += 1
        shifted += not is_working_day(payable.payment_due_date)
        got = payments.get(pid, [])
        assert len(got) == 1, f"COGS payable {payable.description} due {payable.payment_due_date}: {len(got)} payments"
        assert got[0].date == due and got[0].amount == payable.amount_currency
        assert payable.status == CogsPayableStatus.PAID
    assert checked >= 2          # two accounts; the 2024-02-29 accruals fall due 30 Mar (Saturday) and are paid Monday 1 Apr
    for pid, payable in store.cogs.items():  # nothing is paid before it is due
        for t in payments.get(pid, []):
            assert t.date >= payable.payment_due_date


# ---------------------------------------------------------------- phase 5: VAT settlement through the real pipeline

VAT_WINDOW_START = date(2024, 6, 3)    # term 3 (may-jun) ends on SUNDAY 30 Jun 2024; due 31 Aug (Saturday) -> paid Mon 2 Sep
VAT_WINDOW_END = date(2024, 9, 3)      # a Tuesday


@pytest.fixture(scope="module")
def vat_stores():
    weekdays = _run(_days(VAT_WINDOW_START, VAT_WINDOW_END, working_only=True), start=VAT_WINDOW_START)
    every_day = _run(_days(VAT_WINDOW_START, VAT_WINDOW_END, working_only=False), start=VAT_WINDOW_START)
    return weekdays, every_day


def test_vat_term_is_settled_on_its_last_calendar_day_even_when_that_is_a_sunday(vat_stores):
    weekdays, every_day = vat_stores
    assert (2024, 3) in weekdays.vat and (2024, 3) in every_day.vat
    voucher = weekdays.vat_vouchers[(2024, 3)]
    assert voucher.date == date(2024, 6, 30)              # a Sunday: the Monday catch-up books it with its own date
    assert (weekdays.vat[(2024, 3)].output_vat, weekdays.vat[(2024, 3)].input_vat) == (
        every_day.vat[(2024, 3)].output_vat, every_day.vat[(2024, 3)].input_vat)
    assert weekdays.vat[(2024, 3)].output_vat > 0
    # term 4 (jul-aug) closes on Saturday 31 Aug and is caught up by the Monday run, with its own date
    assert weekdays.vat_vouchers[(2024, 4)].date == date(2024, 8, 31)
    assert weekdays.vat[(2024, 4)].period_end == every_day.vat[(2024, 4)].period_end == date(2024, 8, 31)


def test_vat_payment_is_booked_once_on_the_working_day_after_a_weekend_due_date(vat_stores):
    for store in vat_stores:
        settlement = store.vat[(2024, 3)]
        assert settlement.payment_date == date(2024, 9, 2)          # 31 Aug is a Saturday
        payments = [t for t in store.payments.values() if t.vat_settlement_id == settlement.id]
        assert len(payments) == 1
        payment = payments[0]
        assert payment.date == date(2024, 9, 2) and is_working_day(payment.date)
        assert payment.amount == abs(settlement.balance)
        assert (payment.transaction_type == BankTransactionType.OUTGOING) == (settlement.balance > 0)
        assert settlement.status == VatSettlementStatus.PAID
