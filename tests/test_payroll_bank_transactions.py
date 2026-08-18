"""Krok 2 — naprawa: payroll nigdy nie generował transakcji bankowej
OUTGOING (luka od Tier 2, nie regresja Fazy 6, zob. SESSION_HANDOFF.md).

Offline (bez żywej bazy, zgodnie z konwencją reszty pakietu — zob.
tests/test_repository.py) — zamiast zapytania `NOT EXISTS ... JOIN
salary_transaction_id` na prawdziwej bazie (jak sugerował prompt), testuje
bezpośrednio generate_payroll_bank_transaction() dla reprezentatywnego
zakresu historycznych miesięcy: deterministyczne (bez losowości w
payrollu), więc wynik jest identyczny niezależnie od tego, czy dane
faktycznie są w bazie."""

from datetime import date

import pytest

from norfingen.generators.bank_transaction_generator import (
    ACCOUNT_BANK,
    PAYROLL_LIABILITY_ACCOUNTS,
    generate_payroll_bank_transaction,
)
from norfingen.generators.salary_generator import generate_monthly_salary
from norfingen.models.bank_transaction import BankTransactionType

# Próbka obejmująca styczeń (zwykły miesiąc) i czerwiec (feriepenger,
# inna struktura postingów) dla kilku lat z różną liczbą pracowników.
REPRESENTATIVE_MONTHS = [
    (2019, 1), (2019, 6),
    (2022, 6), (2022, 9),  # miesiąc fuzji
    (2025, 1), (2025, 6),
    (2026, 1), (2026, 6),
]


@pytest.mark.parametrize("year,month", REPRESENTATIVE_MONTHS)
def test_generate_payroll_bank_transaction_for_historical_month(year, month):
    transaction, vouchers = generate_monthly_salary(year, month)
    transaction.id = 12345  # symulacja prawdziwego ID z bazy (wymagane przez assert)

    result = generate_payroll_bank_transaction(transaction, vouchers)

    assert result is not None, f"{year}-{month:02d}: brak wypłaty payrollu dla niepustej listy płac"
    bank_transaction, voucher = result

    assert bank_transaction.transaction_type == BankTransactionType.OUTGOING
    assert bank_transaction.salary_transaction_id == 12345
    assert bank_transaction.date == transaction.date
    assert bank_transaction.amount > 0

    # Voucher musi się bilansować (suma postingów = 0) i dotykać wyłącznie
    # kont bilansowych (zobowiązania 2700/2710/2740 + bank 1910) — NIGDY
    # kont P&L (4xxx/5xxx/6xxx/7xxx) — bo ta naprawa nie może zmienić marży.
    assert abs(sum(p.amount for p in voucher.postings)) < 0.01
    for posting in voucher.postings:
        assert posting.account.number in (*PAYROLL_LIABILITY_ACCOUNTS, ACCOUNT_BANK)
        assert not (4000 <= posting.account.number <= 7999)


def test_generate_payroll_bank_transaction_requires_real_id():
    """Zabezpieczenie: świeżo wygenerowany SalaryTransaction (id=None, jeszcze
    niezapisany do bazy) nie może zostać użyty do zbudowania płatności —
    salary_transaction_id FK musiałby wskazywać donikąd."""
    transaction, vouchers = generate_monthly_salary(2024, 3)
    assert transaction.id is None
    with pytest.raises(AssertionError):
        generate_payroll_bank_transaction(transaction, vouchers)


def test_payroll_bank_transaction_total_matches_liability_postings():
    """Kwota płatności = dokładnie suma tego, co zaksięgowano jako
    zobowiązanie (2710+2740+2700) w oryginalnych voucherach listy płac —
    nie inna, niezależnie policzona wartość (zob. docstring funkcji:
    unika duplikowania logiki obliczeniowej)."""
    transaction, vouchers = generate_monthly_salary(2025, 3)
    transaction.id = 1
    bank_transaction, _ = generate_payroll_bank_transaction(transaction, vouchers)

    expected = round(sum(
        -p.amount for v in vouchers for p in v.postings
        if p.account.number in PAYROLL_LIABILITY_ACCOUNTS and p.amount < 0
    ), 2)
    assert bank_transaction.amount == expected
