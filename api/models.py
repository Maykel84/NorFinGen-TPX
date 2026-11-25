"""Modele odpowiedzi Pydantic — typują JSON zwracany przez każdy endpoint,
żeby /docs (OpenAPI/Swagger) generowało czytelne schematy bez ręcznego opisu."""

from datetime import date
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    limit: int
    offset: int
    total: int = Field(description="Łączna liczba pasujących rekordów (przed limit/offset)")


class PLMonthly(BaseModel):
    month: str = Field(description="Format YYYY-MM")
    revenue: float | None = None
    labor_cost: float | None = None
    operating_cost: float | None = None
    cogs: float | None = None
    operating_result: float | None = None
    is_partial: bool | None = Field(
        default=None,
        description="True dla miesiąca, który jeszcze się nie skończył (koszty płac i COGS księgowane są na koniec "
        "miesiąca, więc wynik jest zawyżony). Wskaźniki 12M/YTD pomijają takie miesiące.",
    )
    depreciation: float | None = Field(
        default=None, description="Amortyzacja (konta 60xx). Zawarta w operating_cost, więc operating_result to EBIT."
    )
    ebitda: float | None = Field(default=None, description="operating_result + depreciation")
    financial_result: float | None = Field(
        default=None, description="Wynik finansowy (konta 8000-8299, np. odsetki od pożyczki): przychód dodatni, koszt ujemny."
    )
    tax: float | None = Field(default=None, description="Podatek dochodowy (konta 83xx), kwota dodatnia; księgowany 31.12.")
    net_result: float | None = Field(default=None, description="operating_result + financial_result - tax")


class PLTrailing(BaseModel):
    period_from: str = Field(description="Pierwszy miesiąc okna, YYYY-MM")
    period_to: str = Field(description="Ostatni PEŁNY miesiąc okna, YYYY-MM")
    months: int
    revenue: float
    labor_cost: float
    operating_cost: float
    cogs: float
    operating_result: float
    margin_pct: float | None = Field(default=None, description="operating_result / revenue * 100")


class PLYearly(BaseModel):
    year: int
    revenue: float
    labor_cost: float
    operating_cost: float
    cogs: float
    operating_result: float
    margin_pct: float | None = Field(default=None, description="operating_result / revenue * 100")
    months_included: int = Field(default=12, description="Liczba PEŁNYCH miesięcy w sumie (bieżący, niepełny miesiąc jest pominięty)")


class Customer(BaseModel):
    id: int
    customer_number: str
    name: str
    city: str | None = None
    segment: str | None = None
    onboarding_date: date | None = None
    churn_date: date | None = None
    nace_code: str | None = None
    nace_name: str | None = None
    postal_code: str | None = None
    active: bool


class Headcount(BaseModel):
    month: str = Field(description="Format YYYY-MM")
    active_employees: int


class OrderSummary(BaseModel):
    order_id: int
    customer_id: int
    customer_number: str
    customer_name: str
    order_date: date
    invoice_date: date
    segment: str | None = None
    amount_excluding_vat: float
    amount_including_vat: float


class LifeEvent(BaseModel):
    scope: str = Field(description="'client' lub 'company'")
    code: str
    year: int
    month: int
    customer_number: str | None = None
    customer_name: str | None = None
    segment: str | None = None
    detail: str | None = None


class HealthStatus(BaseModel):
    status: str
    database: str


class KeyRequest(BaseModel):
    label: str = Field(
        min_length=2, max_length=100, description="Twoje imię lub identyfikator kursu"
    )


class KeyResponse(BaseModel):
    api_key: str
    rate_limit_per_hour: int
    message: str


class DbAccessRequest(BaseModel):
    label: str = Field(
        min_length=2, max_length=100, description="Twoje imię lub identyfikator kursu"
    )


class DbAccessResponse(BaseModel):
    host: str
    port: int
    database: str
    username: str
    password: str
    message: str
