"""Generator of additional operating costs (Phase 3): canteen, representation,
transport (mileage + conferences), customer-implementation equipment (COGS).
Phase 6 adds two further COGS costs: Microsoft/Azure pass-through for S02
and, after the first failed sanity-check, tools/licenses pass-through for S01.

Most of these costs (canteen/representation/transport/implementation
equipment) have NO corresponding purchase invoice — direct cash costs of the
company, booked directly: a Voucher with 2 postings (DR cost account / CR
1910 Bankinnskudd), no VAT (_simple_cost_voucher). Azure COGS (Phase 6) uses
a different pattern (_cogs_accrual_voucher: DR COGS account / CR 2400
Leverandørgjeld) — it models a liability owed to a supplier (Microsoft), not
an immediate cash payment, deliberately without a separate
SupplierInvoice/bank_transaction (see SESSION_HANDOFF.md, Phase 6).

Amounts (roster.CANTEEN_SUBSIDY_PER_EMPLOYEE_MONTHLY,
REPRESENTATION_COST_PER_*_CLIENT_MONTHLY, KM_RATE_2019,
CONFERENCE_HOTEL_RATES) are deliberately modest — a lesson from Phase 2
(transcribing prices verbatim without verifying margin crashed the result
to -183%). Implementation equipment (Phase 3, account 4290) — a one-off at
Enterprise/Mid-market customer onboarding. Azure COGS (Phase 6, account
4291) — scales monthly with the number of active S02 customers
(roster.calc_azure_cogs_monthly), replacing the flat Phase 2 Azure cost
(35,000 NOK/month fixed). S01 COGS (Phase 6, account 4292) — scales monthly
with ALL active customers (roster.calc_s01_cogs_monthly) — added after an
offline sanity-check showed that S02-only COGS cannot physically close the
gap between actual revenue (52.4M NOK, not the assumed 35M) and the
headcount~17/margin 7% target (see roster.py, the comment on
calc_s01_cogs_monthly, and SESSION_HANDOFF.md for the full derivation).
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from norfingen.generators.client_events import (
    customer_event_state_asof,
    effective_customer_services,
    event_aware_is_customer_active,
)
from norfingen.generators.company_events import ACCOUNT_UNEXPECTED_COST, unprofitable_quarter_cost_spike
from norfingen.generators.order_generator import apply_annual_inflation
from norfingen.generators.voucher import (
    Posting, Voucher, VoucherType, acct, assert_voucher_valid, expected_vat_amount,
)
from norfingen.models.base import TripletexRef
from norfingen.models.supplier_invoice import PURCHASE_VAT_TYPE_REF
from norfingen.models.cogs_payable import CogsPayable
from norfingen.seed.payroll import active_employees, first_working_day_of_month, last_working_day
from norfingen.seed.workdays import is_working_day, next_working_day, previous_working_day
from norfingen.seed.roster import (
    CONFERENCE_HOTEL_RATES,
    CUSTOMERS,
    CustomerSeed,
    active_customers,
    calc_azure_cogs_monthly,
    calc_canteen_cost,
    calc_client_visit_transport,
    calc_representation_cost,
    calc_s01_cogs_monthly,
    COGS_SUPPLIER_BY_ACCOUNT,
    numeric_id,
)

ACCOUNT_BANK = 1910
ACCOUNT_LEVERANDORGJELD = 2400
ACCOUNT_INPUT_VAT = 2710  # Inngående merverdiavgift (input VAT) - audit 2026-11-16, phase 2
ACCOUNT_OUTPUT_VAT = 2700  # Utgående merverdiavgift - the reverse-charge leg
ACCOUNT_CANTEEN = 7350  # Kantinetilskudd
ACCOUNT_REPRESENTATION = 7420  # Representasjon
ACCOUNT_TRANSPORT = 7000  # Reisekostnader — an existing account (shared with L07 Avis,
# see the module-level docstring of supplier_invoice_generator: no "mix" to split out,
# mileage/conferences are simply new subcategories of the same NS4102 line item)
ACCOUNT_SERVICE_EQUIPMENT = 4290  # Driftsmateriell for kundeleveranse (COGS)
ACCOUNT_AZURE_COGS = 4291  # Videresalgskostnad Microsoft/Azure (COGS, Phase 6)
ACCOUNT_S01_COGS = 4292  # Driftskostnad Managed IT Support — RMM/EDR/tools (COGS, Phase 6, 2nd calibration)

# Phase 4: a COGS accrual is a liability to a supplier, so it has a due date like any purchase invoice. 30 days from the
# accrual, the same term the purchase invoices use (SupplierInvoice.paymentDueDate), moved to the next working day when
# the payment is booked. Suppliers are paid on the due date - there is no late-payment model for them - so COGS follows.
COGS_PAYMENT_TERMS_DAYS = 30

CONFERENCE_MONTHS = {3, 9, 11}
CONFERENCE_PROBABILITY = 0.6
CONFERENCE_TICKET_MIN = 3_000.0
CONFERENCE_TICKET_MAX = 8_000.0
CONFERENCE_PER_DIEM_PER_NIGHT = 750.0

SERVICE_EQUIPMENT_COST_RANGE = {
    "Enterprise": (45_000.0, 90_000.0),
    "Mid-market": (15_000.0, 35_000.0),
}

MONTH_NAMES_NO = [
    "januar", "februar", "mars", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "desember",
]


def _random_working_day(year: int, month: int, first_day: int, last_day: int, key: str) -> date:
    """A reproducible working day of the month in [first_day, last_day]. Its own stream per (month, key): the amount
    streams are untouched, so moving a cost to another day never moves an amount (golden hash of amounts)."""
    rng = random.Random(f"opex-date-{year}-{month}-{key}")
    days = [date(year, month, d) for d in range(first_day, last_day + 1) if is_working_day(date(year, month, d))]
    return rng.choice(days)


def _onboarding_booking_date(onboarding: date) -> date:
    """The onboarding date itself; a weekend moves to the preceding Friday, or to the following Monday when that
    would leave the month (the monthly slice is keyed by month)."""
    shifted = previous_working_day(onboarding)
    return shifted if shifted.month == onboarding.month else next_working_day(onboarding)


def _simple_cost_voucher(on_date: date, account_number: int, description: str, amount: float) -> Voucher:
    """A 2-posting Voucher: DR cost account / CR 1910 Bankinnskudd, no VAT
    (a cash cost paid directly, with no intermediate SupplierInvoice document)."""
    amount = round(amount, 2)
    voucher = Voucher(
        date=on_date,
        description=description,
        voucherType=VoucherType.OPERATING_COST,
        postings=[
            Posting(date=on_date, account=acct(account_number), amount=amount),
            Posting(date=on_date, account=acct(ACCOUNT_BANK), amount=-amount),
        ],
    )
    assert_voucher_valid(voucher)
    return voucher


def _cash_purchase_voucher(on_date: date, account_number: int, description: str, net: float) -> Voucher:
    """A domestic purchase paid from the bank at once, WITH input VAT (audit 2026-11-16, phase 2; account 4290):

        Dr cost account   net     (vatType 1, vatAmount = the VAT contained in the line)
        Dr 2710           VAT     (own posting, 25 % of net - the supplier invoices' pattern)
        Cr 1910           gross

    No supplier: this is operating material bought for a customer delivery, not an invoice from an identified supplier,
    so supplier_id stays NULL. The net amount is the figure the voucher carried before the VAT existed."""
    net = round(net, 2)
    vat = expected_vat_amount(net)
    voucher = Voucher(
        date=on_date,
        description=description,
        voucherType=VoucherType.OPERATING_COST,
        postings=[
            Posting(date=on_date, account=acct(account_number), amount=net, vatType=PURCHASE_VAT_TYPE_REF, vatAmount=vat),
            Posting(date=on_date, account=acct(ACCOUNT_INPUT_VAT), amount=vat, vatType=PURCHASE_VAT_TYPE_REF),
            Posting(date=on_date, account=acct(ACCOUNT_BANK), amount=-round(net + vat, 2)),
        ],
    )
    assert_voucher_valid(voucher)
    return voucher


def _cogs_accrual_voucher(on_date: date, account_number: int, description: str, net: float) -> Voucher:
    """COGS accrual from a domestic supplier, with input VAT (audit 2026-11-16, phase 2):

        Dr 4291|4292   net     (vatType 1, vatAmount = VAT, supplier)
        Dr 2710        VAT     (own posting, 25 % of net)
        Cr 2400        gross   (supplier)

    The net amount is exactly what the voucher carried before phase 2 (golden hash opex_net_amounts), so the cost and the
    margin do not move; the VAT is an asset (a receivable from Skatteetaten) and the liability to the supplier grows to the
    gross amount. Unlike _simple_cost_voucher this is a liability owed to a supplier, analogous to a purchase invoice, but
    without a SupplierInvoice document (phase 4 gives it a CogsPayable instead)."""
    net = round(net, 2)
    vat = expected_vat_amount(net)
    # The supplier dimension on 2400 is what accounts-payable ageing needs: 4291 -> L01 Microsoft Norge, 4292 -> L09
    # Ingram Micro (roster.COGS_SUPPLIER_BY_ACCOUNT).
    supplier = TripletexRef(id=numeric_id(COGS_SUPPLIER_BY_ACCOUNT[account_number]))
    voucher = Voucher(
        date=on_date,
        description=description,
        voucherType=VoucherType.OPERATING_COST,
        postings=[
            Posting(date=on_date, account=acct(account_number), amount=net, vatType=PURCHASE_VAT_TYPE_REF,
                    vatAmount=vat, supplier=supplier),
            Posting(date=on_date, account=acct(ACCOUNT_INPUT_VAT), amount=vat, vatType=PURCHASE_VAT_TYPE_REF,
                    supplier=supplier),
            Posting(date=on_date, account=acct(ACCOUNT_LEVERANDORGJELD), amount=-round(net + vat, 2), supplier=supplier),
        ],
    )
    assert_voucher_valid(voucher)
    return voucher


def _reverse_charge_cogs_voucher(on_date: date, account_number: int, description: str, net: float,
                                 supplier: TripletexRef) -> Voucher:
    """COGS accrual from a FOREIGN supplier: reverse charge (omvendt avgiftsplikt), prepared for the future.

        Dr cost account  net  / Cr 2400  net     (the supplier is owed the net amount only)
        Dr 2710          VAT  / Cr 2700  VAT     (equal amounts: input and output VAT cancel, the VAT return is unchanged)

    No supplier in the roster is foreign today, so the generator never calls this; it exists, and is tested, so that the
    first foreign supplier does not get domestic VAT by mistake."""
    net = round(net, 2)
    vat = expected_vat_amount(net)
    voucher = Voucher(
        date=on_date,
        description=description,
        voucherType=VoucherType.OPERATING_COST,
        postings=[
            Posting(date=on_date, account=acct(account_number), amount=net, supplier=supplier),
            Posting(date=on_date, account=acct(ACCOUNT_LEVERANDORGJELD), amount=-net, supplier=supplier),
            Posting(date=on_date, account=acct(ACCOUNT_INPUT_VAT), amount=vat, vatType=PURCHASE_VAT_TYPE_REF),
            Posting(date=on_date, account=acct(ACCOUNT_OUTPUT_VAT), amount=-vat, vatType=PURCHASE_VAT_TYPE_REF),
        ],
    )
    assert_voucher_valid(voucher)
    return voucher


def cogs_payable_for(voucher: Voucher) -> CogsPayable | None:
    """The payable that goes with a COGS accrual voucher - None for every other operating-cost voucher.

    An accrual is recognised by its credit to 2400 (the cash costs - canteen, transport, equipment - credit the bank,
    1910, and are paid the moment they are booked). amount_currency = what was credited to 2400 (gross), so paying the
    payable clears the liability to the cent; the net cost and the VAT are kept beside it."""
    if voucher.voucherType != VoucherType.OPERATING_COST:
        return None
    credit = next((p for p in voucher.postings if p.account.number == ACCOUNT_LEVERANDORGJELD and p.amount < 0), None)
    if credit is None:
        return None
    cost = next(p for p in voucher.postings if p.amount > 0 and p.account.number != ACCOUNT_INPUT_VAT)
    vat = round(sum(p.amount for p in voucher.postings if p.account.number == ACCOUNT_INPUT_VAT), 2)
    return CogsPayable(
        accrual_date=voucher.date,
        payment_due_date=voucher.date + timedelta(days=COGS_PAYMENT_TERMS_DAYS),
        account_number=cost.account.number,
        supplier_id=credit.supplier.id,
        description=voucher.description or "",
        amount_excluding_vat_currency=round(cost.amount, 2),
        vat_amount_currency=vat,
        amount_currency=round(-credit.amount, 2),
    )


def generate_conference_trip(year: int, month: int, rng: random.Random) -> dict | None:
    """2-3 conference trips per year (e.g. NKUL, Sikkerhetsfestivalen,
    Microsoft Ignite Tour Norway). Tickets + hotel + per diem. Deterministic
    — a local rng passed in by the caller (random.Random(string), not the
    global random or the built-in hash())."""
    if month not in CONFERENCE_MONTHS:
        return None
    if rng.random() > CONFERENCE_PROBABILITY:
        return None
    city = rng.choice(["Oslo", "Bergen", "Trondheim"])
    nights = rng.choice([1, 2])
    hotel_cost = CONFERENCE_HOTEL_RATES[city] * nights
    ticket_cost = rng.uniform(CONFERENCE_TICKET_MIN, CONFERENCE_TICKET_MAX)
    per_diem = CONFERENCE_PER_DIEM_PER_NIGHT * nights
    return {
        "description": f"Konferansereise {city}",
        "amount": round(hotel_cost + ticket_cost + per_diem, 2),
    }


def should_generate_service_equipment_purchase(customer: CustomerSeed, month: int, rng: random.Random | None = None) -> bool:
    """Equipment purchased for customer implementation (routers, servers,
    network devices) — Enterprise/Mid-market only (SMB has only S01, a
    smaller implementation scope with no dedicated equipment). Checks ONLY
    the month — whether it's the correct onboarding YEAR (so the cost
    doesn't repeat every year in the same month) is decided by the caller
    (generate_monthly_opex), see its docstring. The rng parameter is kept
    for signature compatibility with the task — the predicate is fully
    deterministic from date/segment, unused."""
    return month == customer.onboarding_date.month and customer.segment in ("Enterprise", "Mid-market")


def calc_service_equipment_cost(customer: CustomerSeed) -> float:
    """A one-off implementation cost at onboarding. Deterministic
    (random.Random(string) seeded with the customer number, NOT the global
    random.uniform from the task's pseudocode — that would break backfill
    reproducibility across runs, see SESSION_HANDOFF.md item 6)."""
    rng = random.Random(f"service-equipment-{customer.number}")
    low, high = SERVICE_EQUIPMENT_COST_RANGE[customer.segment]
    return round(rng.uniform(low, high), -2)


def generate_monthly_opex(year: int, month: int) -> list[Voucher]:
    """Generates all new Phase 3 operating costs for one month: canteen
    (every month), representation (every month, per active
    Enterprise/Mid customer), mileage (seasonal), conferences (selected
    months in Q1/Q3, random), implementation equipment (only in the month
    of the customer's FIRST onboarding YEAR —
    should_generate_service_equipment_purchase checks only the month, so
    the extra `customer.onboarding_date.year == year` condition here
    prevents the cost from repeating every year)."""
    on_date = date(year, month, 1)  # month anchor for "who is active"; NOT the booking date of the entries below
    month_end = last_working_day(year, month)  # payroll day: month-end entries are booked together with payroll
    month_label = f"{MONTH_NAMES_NO[month - 1]} {year}"
    vouchers: list[Voucher] = []

    # first_working_day_of_month(), not on_date (the calendar 1st) — Phase
    # 5: EMPLOYEES.start_date is sometimes the 2nd/3rd calendar day (if the
    # 1st is a weekend), so on_date would wrongly exclude a new employee
    # from their own start month.
    employee_count = len(active_employees(first_working_day_of_month(year, month)))
    if employee_count > 0:
        canteen_cost = calc_canteen_cost(employee_count)
        vouchers.append(_simple_cost_voucher(month_end, ACCOUNT_CANTEEN, f"Kantinetilskudd {month_label}", canteen_cost))

    # Phase 7, Task 2c — active_customers() only knows the static
    # churn_date; we additionally apply event_aware_is_customer_active, so
    # all the per-customer costs in this function
    # (representation/transport/S01/S02 COGS) stop accruing for a customer
    # after BANKRUPTCY (client_events), the same as revenue in
    # order_generator — otherwise the company keeps paying
    # Microsoft/for tools on behalf of a customer that no longer exists,
    # artificially depressing margin.
    customers = [c for c in active_customers(on_date) if event_aware_is_customer_active(c, on_date)]

    representation_base = calc_representation_cost(customers)
    if representation_base > 0:
        representation_cost = apply_annual_inflation(representation_base, year)
        vouchers.append(_simple_cost_voucher(
            _random_working_day(year, month, 5, 25, "representation"), ACCOUNT_REPRESENTATION, f"Representasjon {month_label}", representation_cost))

    transport_cost = calc_client_visit_transport(customers, month)
    if transport_cost > 0:
        vouchers.append(_simple_cost_voucher(month_end, ACCOUNT_TRANSPORT, f"Kjøregodtgjørelse — kundebesøk {month_label}", transport_cost))

    # Phase 6 — S02 COGS pass-through (replaces the flat Azure cost from
    # Phase 2). Phase 7, Task 2c — calc_azure_cogs_monthly computes the cost
    # BY SEGMENT (assuming every Enterprise/Mid-market customer buys S02 —
    # true under the standard bundle, roster.SEGMENT_SERVICE_BUNDLES), so a
    # customer whose S02 was removed by OFFER_REDUCTION must be excluded
    # from this list here — otherwise the company would keep paying
    # Microsoft for a service the customer no longer pays us for (exactly
    # the bug that was depressing margin before the fix, see
    # SESSION_HANDOFF.md).
    s02_customers = [
        c for c in customers
        if "S02" in effective_customer_services(c, customer_event_state_asof(c.number, year, month))
    ]
    azure_cogs_base = calc_azure_cogs_monthly(s02_customers)
    if azure_cogs_base > 0:
        azure_cogs_cost = apply_annual_inflation(azure_cogs_base, year)
        vouchers.append(_cogs_accrual_voucher(
            month_end, ACCOUNT_AZURE_COGS, f"Videresalgskostnad Microsoft/Azure {month_label}", azure_cogs_cost,
        ))

    # Phase 6, second calibration — S01 COGS pass-through (all segments, see
    # roster.calc_s01_cogs_monthly for the market-based rationale).
    s01_cogs_base = calc_s01_cogs_monthly(customers)
    if s01_cogs_base > 0:
        s01_cogs_cost = apply_annual_inflation(s01_cogs_base, year)
        vouchers.append(_cogs_accrual_voucher(
            month_end, ACCOUNT_S01_COGS, f"Driftskostnad Managed IT Support {month_label}", s01_cogs_cost,
        ))

    conference_rng = random.Random(f"conference-{year}-{month}")
    trip = generate_conference_trip(year, month, conference_rng)
    if trip is not None:
        vouchers.append(_simple_cost_voucher(
            _random_working_day(year, month, 8, 25, "conference"), ACCOUNT_TRANSPORT, trip["description"], trip["amount"]))

    for customer in CUSTOMERS:
        if customer.onboarding_date.year == year and should_generate_service_equipment_purchase(customer, month):
            equipment_cost = calc_service_equipment_cost(customer)
            vouchers.append(_cash_purchase_voucher(
                _onboarding_booking_date(customer.onboarding_date), ACCOUNT_SERVICE_EQUIPMENT,
                f"Driftsmateriell for kundeleveranse — {customer.number}", equipment_cost,
            ))

    # Phase 7, Task 3c — UNPROFITABLE_QUARTER: a one-off cost spike, booked
    # EXACTLY in the randomly rolled month (not repeated every month of the
    # quarter — it's the hours_generator ticket reduction that's spread
    # across the whole quarter, the cost is "one-off" per the task).
    cost_spike = unprofitable_quarter_cost_spike(year, month)
    if cost_spike is not None:
        vouchers.append(_simple_cost_voucher(
            _random_working_day(year, month, 8, 25, "cost-spike"), ACCOUNT_UNEXPECTED_COST, f"Uforutsett driftskostnad — svakt kvartal {month_label}", cost_spike,
        ))

    return vouchers
