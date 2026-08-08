"""Dodatek — kody branżowe NACE/SN2007 (czysto opisowy, nie wpływa na przychód/koszty/marżę)."""

from norfingen.seed.roster import (
    COMPANY_NACE_CODE,
    COMPANY_NACE_NAME,
    CUSTOMER_NACE,
    CUSTOMERS,
    customer_nace,
)


def test_company_has_nace_code():
    assert COMPANY_NACE_CODE == "62.020"
    assert "informasjonsteknologi" in COMPANY_NACE_NAME.lower()


def test_all_customers_have_nace_code():
    """Każdy klient (aktywny i z churn) ma przypisany kod NACE — format XX.XXX."""
    for customer in CUSTOMERS:
        nace = customer_nace(customer)
        assert nace.code is not None
        assert len(nace.code) >= 6  # "XX.XXX"
        assert "." in nace.code
        assert nace.name


def test_nace_codes_are_diverse():
    """Klienci nie mają wszyscy tego samego kodu."""
    codes = {v.code for v in CUSTOMER_NACE.values()}
    assert len(codes) >= 6  # co najmniej 6 różnych sektorów


def test_nace_mapping_covers_exactly_all_customers():
    """CUSTOMER_NACE nie ma braków ani osieroconych wpisów względem CUSTOMERS."""
    customer_numbers = {c.number for c in CUSTOMERS}
    assert set(CUSTOMER_NACE.keys()) == customer_numbers
