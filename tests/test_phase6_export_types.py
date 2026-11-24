"""Phase 6 (docs/SPEC_poprawki_ksiegowe.md): types and empty columns of the export."""

import io
from decimal import Decimal

import openpyxl

from api.export_data import _COLUMNS, _excel_cell, _format_decimal_columns
from export_queries import QUERIES
from norfingen.seed.roster import ALL_SUPPLIERS, SUPPLIER_ADDRESSES


def test_every_supplier_has_a_static_postal_code_and_city():
    assert set(SUPPLIER_ADDRESSES) == {s.number for s in ALL_SUPPLIERS}
    for number, (postal_code, city, source) in SUPPLIER_ADDRESSES.items():
        assert len(postal_code) == 4 and postal_code.isdigit(), number
        assert city and source in ("brreg", "illustrative"), number


def test_registry_sourced_codes_belong_only_to_suppliers_with_an_organisation_number():
    """'brreg' = looked up by organisation number, so a supplier without one cannot be 'brreg'; and every supplier that HAS
    a number was looked up."""
    for supplier in ALL_SUPPLIERS:
        source = SUPPLIER_ADDRESSES[supplier.number][2]
        assert (source == "brreg") == (supplier.real_org_number is not None), supplier.number


def test_the_generator_makes_no_registry_call():
    """The codes are static data in the repo. Nothing under src/ imports an HTTP client, so nothing can call the registry."""
    from pathlib import Path
    for path in Path(__file__).resolve().parents[1].joinpath("src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "requests" not in text and "urllib.request" not in text and "httpx" not in text, path


def test_purchase_invoice_export_carries_the_supplier_postal_code():
    assert "s.postal_code" in QUERIES["Faktury_zakupu"] and "postal_code" in _COLUMNS["Faktury_zakupu"]


def test_gl_export_has_voucher_number_and_no_employee_id():
    columns = list(_COLUMNS["Postingi_GL"])
    assert "voucher_number" in columns and "employee_id" not in columns
    assert "v.id AS voucher_number" in QUERIES["Postingi_GL"] and "employee_id" not in QUERIES["Postingi_GL"]
    assert columns == ["date", "voucher_number", "voucher_type", "description", "account_number", "amount",
                       "vat_amount", "customer_id", "supplier_id"]


def test_numbers_are_written_as_numbers_and_count_is_shown_with_two_decimals():
    assert _excel_cell(Decimal("115.50")) == 115.5 and isinstance(_excel_cell(Decimal("1.00")), float)
    assert _excel_cell(7) == 7 and _excel_cell(None) is None and _excel_cell("x") == "x" and _excel_cell(True) is True and _excel_cell(False) is False

    wb = openpyxl.Workbook()
    ws = wb.active
    columns = ["order_id", "count", "amount_currency"]
    ws.append(columns)
    for row in ([1, Decimal("1.00"), Decimal("1250.00")], [2, Decimal("115.50"), Decimal("144375.00")]):
        ws.append([_excel_cell(v) for v in row])
    _format_decimal_columns(ws, columns)
    buf = io.BytesIO()
    wb.save(buf)
    ws2 = openpyxl.load_workbook(io.BytesIO(buf.getvalue())).active
    assert [c.value for c in ws2["B"][1:]] == [1.0, 115.5]            # numeric, fractional part kept
    assert all(c.number_format == "0.00" for c in ws2["B"][1:])
    assert ws2["A2"].number_format == "General"


def test_dates_are_real_excel_dates_and_postal_codes_stay_text():
    """Audit 2026-11-16, phase 6. The database types were already right (DATE, TEXT, INTEGER, NUMERIC); the export wrote every
    date as text. Now a date is a date cell, a timestamp stays text, and a postal code is text with an explicit text format, so
    "0194" cannot lose its zero in Excel."""
    from datetime import date, datetime

    import openpyxl

    import api.export_data as api_export
    # export_excel.py is a script (it connects to the database on import), so only the REST API's copy of the two helpers is
    # imported here; the local script carries the same code and was checked by hand against a real export.
    for cell in (api_export._excel_cell,):
        assert cell(date(2026, 11, 15)) == date(2026, 11, 15) and type(cell(date(2026, 11, 15))) is date
        assert cell(datetime(2026, 11, 15, 10, 0)) == "2026-11-15 10:00:00"  # a datetime is not mistaken for a date
        assert cell("0194") == "0194"

    for fmt in (api_export._format_decimal_columns,):
        ws = openpyxl.Workbook().active
        ws.append(["postal_code", "invoice_date"])
        ws.append(["0194", date(2026, 11, 15)])
        fmt(ws, ["postal_code", "invoice_date"])
        assert ws["A2"].number_format == "@" and ws["A2"].value == "0194"
        assert ws["B2"].number_format == "yyyy-mm-dd"


def test_null_is_an_empty_cell_not_an_empty_string_so_id_and_date_columns_keep_one_type():
    """Round 3 (export of 2026-11-24): NULL used to be written as "", a TEXT cell. customer_id / supplier_id in Postingi_GL
    (and paid_date next to real dates) became mixed text-and-number columns, which BI tools read as float or text. Now a NULL is
    an empty cell, ids are whole numbers, and the whole column has a single type."""
    from datetime import date

    import openpyxl

    import api.export_data as api_export

    ws = openpyxl.Workbook().active
    columns = ["voucher_number", "customer_id", "supplier_id", "paid_date"]
    ws.append(columns)
    for row in ([1, None, 7, date(2026, 1, 2)], [2, 3, None, None]):
        ws.append([api_export._excel_cell(v) for v in row])
    api_export._format_decimal_columns(ws, columns)
    buf = io.BytesIO()
    ws.parent.save(buf)
    ws2 = openpyxl.load_workbook(io.BytesIO(buf.getvalue())).active
    assert [c.value for c in ws2["B"][1:]] == [None, 3] and [c.value for c in ws2["C"][1:]] == [7, None]
    assert ws2["B2"].data_type != "s" and ws2["C3"].data_type != "s"          # no empty STRING in a numeric column
    assert ws2["D3"].value is None and ws2["D2"].data_type == "d"              # no empty string next to real dates
    assert all(c.number_format == "0" for col in "ABC" for c in ws2[col][1:])  # whole numbers, not 7.0
