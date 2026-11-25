"""Round 4, step 1: tools/verify.py - the checks it runs, how it prepares the SQL and how it reports. No database needed."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verify  # noqa: E402


def test_every_statement_of_gl_checks_has_a_description():
    from run_gl_checks import _statements

    sql_text = (ROOT / "tests" / "gl_checks.sql").read_text(encoding="utf-8")
    described = verify.descriptions(sql_text)
    ids = [test_id for test_id, _ in _statements(sql_text)]
    assert len(ids) == 26 and ids[0] == "T1" and "T23" in ids and "REG_B" in ids
    assert all(described.get(i) for i in ids), [i for i in ids if not described.get(i)]


def test_the_export_sheets_are_put_in_front_of_a_plain_select_as_ctes():
    sql = verify.with_export_tables("SELECT 'T1' AS test FROM gl WHERE amount > 1")
    assert sql.startswith("WITH gl AS (") and "sales AS (" in sql and "pay AS (" in sql
    assert sql.rstrip().endswith("WHERE amount > 1")


def test_a_statement_with_its_own_with_keeps_one_with_and_its_own_definitions():
    own = "WITH pay AS (SELECT 1 AS x), span AS (SELECT 2 AS y) SELECT 'T21' FROM pay, span, gl"
    sql = verify.with_export_tables(own)
    assert sql.upper().count("WITH ") == 1                      # one WITH, the CTEs are joined with commas
    assert sql.count("pay AS (") == 1 and "pay AS (SELECT 1 AS x)" in sql   # its own `pay` wins, no clash
    assert "gl AS (" in sql and "sales AS (" in sql


def test_the_extra_quality_checks_are_the_empirion_style_fields():
    ids = [c[0] for c in verify.EXTRA_CHECKS]
    assert ids == ["Q1", "Q2", "Q3", "Q4", "Q5"]
    assert all(sql.lstrip().upper().startswith(("SELECT", "WITH")) for _, _, sql in verify.EXTRA_CHECKS)
    names = [name for name, _ in verify.METRICS]
    for wanted in ("vouchers without lines", "unbalanced vouchers (count)", "unbalanced vouchers (sum of imbalance)",
                   "invoices without lines"):
        assert wanted in names


def test_the_report_marks_failures_and_never_contains_an_address():
    results = [verify.Result("T1", "ledger balances", "PASS", 0),
               verify.Result("T2", "documents balance", "FAIL", 2, [("T2", 17, 0.31)]),
               verify.Result("T3", "broken", "ERROR", 0, ["boom"])]
    metrics = [("vouchers", 7258), ("newest voucher date", "2026-11-24")]
    table = verify.render_table(results)
    assert "1/3 PASS" in table and "FAIL" in table and "ERROR" in table
    md = verify.render_markdown(results, metrics, "2026-11-24", "remote")
    assert md.startswith("# Verification of 2026-11-24") and "**1/3 PASS**" in md and "2 not passing" in md
    assert "## Failures" in md and "T2" in md and "| vouchers | 7258 |" in md
    assert "postgresql" not in md and "supabase" not in md.lower()   # the address is never written


def test_host_kind_hides_the_address():
    assert verify.host_kind("postgresql://u@127.0.0.1:54329/db") == "local"
    assert verify.host_kind("postgresql://u:p@db.example.com:5432/db") == "remote"
