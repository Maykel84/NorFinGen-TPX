"""Voucher + Posting — kręgosłup ledgera (Warstwa 3).

POST /v2/ledger/voucher · POST /v2/ledger/posting

Znak Posting.amount: + = debet, - = kredyt. Suma amount wszystkich postingów
w Voucherze musi wynosić 0. VAT nie jest osobnym postingiem — jest polem
vatAmount na postingu debetowym (konto 2770 zasila Tripletex automatycznie).

Zob. docs/norfingen_warstwa3_schemas.html — 7 wzorców DR/CR (W1-W7) i reguły walidacji.
"""

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field

from norfingen.models.base import TripletexRef

PURCHASE_AND_SALES_VAT_RATE = 0.25  # jedyna stawka używana w NorFinGen (vatCode "1" i "3")


class VoucherType(str, Enum):
    INVOICE = "INVOICE"  # Order z invoiceDate — tworzony automatycznie przez Tripletex
    INCOMING_INVOICE = "INCOMING_INVOICE"  # SupplierInvoice — generator jawnie
    SALARY = "SALARY"  # SalaryTransaction + Feriepenger — generator jawnie
    BANK = "BANK"  # płatności bankowe — Etap 4
    MANUAL = "MANUAL"  # kapitał zakładowy, korekty — backfill
    OPERATING_COST = "OPERATING_COST"  # Faza 3 — kantyna/reprezentacja/transport/sprzęt wdrożeniowy: koszt gotówkowy bez osobnego dokumentu źródłowego (nie SupplierInvoice)


class AccountRef(BaseModel):
    """Referencja do konta GL na Postingu — Tripletex adresuje konto przez number."""

    model_config = ConfigDict(populate_by_name=True)

    number: int
    id: Optional[int] = None


def acct(number: int) -> AccountRef:
    return AccountRef(number=number)


def expected_vat_amount(amount_excluding_vat: float, vat_rate: float = PURCHASE_AND_SALES_VAT_RATE) -> float:
    """Generator liczy VAT od kwoty netto — round(netto × stawka, 2), nigdy odwrotnie z brutto."""
    return round(amount_excluding_vat * vat_rate, 2)


class Posting(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    voucher: Optional[TripletexRef] = None
    date: date
    description: Optional[str] = None
    account: AccountRef
    amount: float  # + debet / - kredyt
    currency: str = "NOK"
    vatType: Optional[TripletexRef] = None
    vatAmount: Optional[float] = None  # tylko na postingu DR — embedded, nie osobny posting
    customer: Optional[TripletexRef] = None  # wymagane dla konta 1500 (AR aging)
    supplier: Optional[TripletexRef] = None  # wymagane dla konta 2400 (AP aging)
    employee: Optional[TripletexRef] = None  # wymagane dla kont 2710/2740 (karta pracownika)
    department: Optional[TripletexRef] = None  # dla kont 5000/5400/3000/3100 (raporty działowe)
    url: Optional[str] = None

    @computed_field  # type: ignore[misc]
    @property
    def amountCurrency(self) -> float:
        return self.amount

    @computed_field  # type: ignore[misc]
    @property
    def vatAmountCurrency(self) -> Optional[float]:
        return self.vatAmount


class Voucher(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    date: date
    description: Optional[str] = None
    voucherType: VoucherType
    postings: list[Posting] = []
    url: Optional[str] = None

    def validate_balance(self, tolerance: float = 0.02) -> bool:
        """Voucher bez VAT: suma amount musi wynosić ~0. Voucher z VAT (np.
        INCOMING_INVOICE: DR excl. VAT vs CR incl. VAT): Tripletex automatycznie
        dokłada trzecią nogę na konto 2770 wyliczoną z pola vatAmount (generator
        NIE tworzy tego postingu ręcznie — zob. docs/norfingen_warstwa3_schemas.html,
        sekcja "Zasada VAT"). Dlatego różnica |suma amount| musi się równać
        |suma vatAmount|, nie literalnemu zeru. Tolerancja domyślna 0.02 NOK
        pokrywa zaokrąglenia groszowe przy przeliczeniach netto/brutto/VAT
        (sama dokumentacja W3 dopuszcza ±1 NOK dla zgodności vatAmount)."""
        total = sum(p.amount for p in self.postings)
        vat_total = sum(p.vatAmount or 0.0 for p in self.postings)
        return abs(abs(total) - abs(vat_total)) <= tolerance


def assert_voucher_valid(voucher: Voucher) -> None:
    """Reguły walidacji 1-3 z docs/norfingen_warstwa3_schemas.html, wywoływane przed
    każdym zapisem Vouchera. Reguła #4 (zgodność vatAmount) jest pilnowana przez
    generatory w miejscu obliczenia (expected_vat_amount), bo tam znana jest
    rzeczywista kwota excl. VAT — nie da się jej wiarygodnie odtworzyć z samego
    znaku Posting.amount (sprzedaż = incl. VAT, zakup = excl. VAT)."""
    assert len(voucher.postings) >= 2, "Voucher wymaga min. 2 postingów"
    assert all(p.account is not None for p in voucher.postings), "Brak konta GL w postingu"
    assert voucher.validate_balance(), "Voucher niezbalansowany"
