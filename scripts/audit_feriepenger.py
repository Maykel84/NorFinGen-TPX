"""
Audyt feriepenger (Faza 5) — weryfikuje poprawność naliczenia dla każdego
pracownika w każdym roku, w którym otrzymał wypłatę czerwcową. Porównuje
rzeczywiste dane z Supabase (salary_transactions/payslips/salary_specifications)
z oczekiwanymi wartościami przeliczonymi przez norfingen.generators.salary_generator
(ten sam kod co backfill — audyt wykrywa rozjazd MIĘDZY danymi w bazie a
aktualną logiką generatora, np. po zmianie roster.py bez ponownego backfillu,
NIE błąd we wzorze samym w sobie).

Sprawdza dla każdego pracownika × każdego roku z wypłatą czerwcową:
1. feriepengegrunnlag (podstawa) = suma rzeczywiście wypłaconego brutto z roku
   poprzedniego, od miesiąca zatrudnienia — brutto_earned_in_year()
2. feriepenger_amount = 12% x feriepengegrunnlag — calc_feriepenger()
3. total_brutto w czerwcu = max(feriepenger, normalna_pensja) — calc_june_salary()
4. pracownicy zatrudnieni w BIEŻĄCYM roku (pierwszy rok stażu, przed pierwszym
   czerwcem) NIE mają wypłaconego feriepenger (podstawa z roku poprzedniego = 0)

Uruchomienie:
    python scripts/audit_feriepenger.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from norfingen.db.repository import get_connection  # noqa: E402
from norfingen.generators.salary_generator import brutto_earned_in_year, calc_june_salary  # noqa: E402
from norfingen.seed.roster import EMPLOYEES, numeric_id  # noqa: E402

FERIEPENGER_WAGE_TYPE_ID = 260
TOLERANCE_NOK = 0.02  # zaokrąglenia groszowe

FETCH_JUNE_FERIEPENGER_SQL = """
    SELECT e.id, st.year, ss.amount
    FROM salary_transactions st
    JOIN payslips p ON p.transaction_id = st.id
    JOIN employees e ON e.id = p.employee_id
    JOIN salary_specifications ss ON ss.payslip_id = p.id
    WHERE st.month = 6 AND ss.wage_type_id = %s
    ORDER BY e.id, st.year
"""

FETCH_JUNE_PAYSLIP_TOTAL_SQL = """
    SELECT e.id, st.year, SUM(ss.amount) FILTER (WHERE ss.wage_type_id IN (100, 260)) AS total_brutto
    FROM salary_transactions st
    JOIN payslips p ON p.transaction_id = st.id
    JOIN employees e ON e.id = p.employee_id
    JOIN salary_specifications ss ON ss.payslip_id = p.id
    WHERE st.month = 6
    GROUP BY e.id, st.year
    ORDER BY e.id, st.year
"""

FETCH_JUNE_PAYSLIP_EXISTS_SQL = """
    SELECT e.id, st.year
    FROM salary_transactions st
    JOIN payslips p ON p.transaction_id = st.id
    JOIN employees e ON e.id = p.employee_id
    WHERE st.month = 6
    ORDER BY e.id, st.year
"""


def audit_employee_feriepenger(employee_id: int, year: int, actual_feriepenger: float, actual_total_brutto: float) -> dict:
    """Sprawdza jednego pracownika w jednym roku (czerwiec = rok `year`)
    względem oczekiwanych wartości przeliczonych z aktualnego roster.py."""
    employee = next(e for e in EMPLOYEES if numeric_id(e.number) == employee_id)
    basis_prev_year = brutto_earned_in_year(employee, year - 1)
    expected = calc_june_salary(employee, year, basis_prev_year)

    issues = []
    if abs(actual_feriepenger - expected.feriepenger) > TOLERANCE_NOK:
        issues.append(
            f"feriepenger: DB={actual_feriepenger:.2f} oczekiwane={expected.feriepenger:.2f} "
            f"(podstawa={basis_prev_year:.2f})"
        )
    if abs(actual_total_brutto - expected.total_brutto) > TOLERANCE_NOK:
        issues.append(f"total_brutto: DB={actual_total_brutto:.2f} oczekiwane={expected.total_brutto:.2f}")

    # Pracownik w pierwszym (niepełnym) roku stażu -> podstawa z roku
    # poprzedniego musi być 0 (zatrudniony w trakcie/po roku `year - 1`).
    if employee.start_date.year >= year:
        if basis_prev_year != 0:
            issues.append(f"oczekiwano basis=0 dla pracownika zatrudnionego w {employee.start_date.year} (rok={year})")

    return {
        "ok": not issues,
        "employee_id": employee_id,
        "employee_number": employee.number,
        "year": year,
        "issues": issues,
    }


def run_full_audit() -> list[dict]:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(FETCH_JUNE_FERIEPENGER_SQL, (FERIEPENGER_WAGE_TYPE_ID,))
        feriepenger_rows = {(emp_id, year): float(amount) for emp_id, year, amount in cur.fetchall()}

        cur.execute(FETCH_JUNE_PAYSLIP_TOTAL_SQL)
        total_brutto_rows = {(emp_id, year): float(total or 0) for emp_id, year, total in cur.fetchall()}

        cur.execute(FETCH_JUNE_PAYSLIP_EXISTS_SQL)
        all_june_payslips = list(cur.fetchall())

    discrepancies = []
    for emp_id, year in all_june_payslips:
        actual_feriepenger = feriepenger_rows.get((emp_id, year), 0.0)
        actual_total_brutto = total_brutto_rows.get((emp_id, year), 0.0)
        result = audit_employee_feriepenger(emp_id, year, actual_feriepenger, actual_total_brutto)
        if not result["ok"]:
            discrepancies.append(result)

    return discrepancies


def main() -> None:
    discrepancies = run_full_audit()
    if not discrepancies:
        print("Audyt feriepenger: BRAK ROZBIEŻNOŚCI — wszystkie wypłaty czerwcowe zgodne z aktualną logiką generatora.")
        return

    print(f"Audyt feriepenger: znaleziono {len(discrepancies)} rozbieżności:")
    for d in discrepancies:
        print(f"  {d['employee_number']} ({d['year']}): {'; '.join(d['issues'])}")


if __name__ == "__main__":
    main()
