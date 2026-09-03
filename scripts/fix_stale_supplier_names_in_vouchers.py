"""Jednorazowa migracja: audyt dostawców względem Brønnøysundregistrene
(Zadanie 1, scripts/audit_supplier_names.py) zmienił dwie nazwy dostawców
w roster.py (L06: literówka poprawiona na "Advokatfirmaet Thommessen AS";
L08: "Nordic Insurance Partners AS" -> "Gjensidige Forsikring ASA", świadomie
fikcyjna zastąpiona realną marką). `seed_reference_data()` poprawnie
zaktualizował `suppliers.name`/`organization_number` (UPSERT), ale
`vouchers.description` jest zapisywany JEDNORAZOWO przy generowaniu
(f"{invoice.invoiceNumber} — {supplier.name}") i nie odświeża się
automatycznie — ten skrypt naprawia TYLKO tekst opisu (nie kwoty, konta,
daty ani żadną logikę finansową) w już istniejących voucherach.

Uruchomienie:
    python scripts/fix_stale_supplier_names_in_vouchers.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import psycopg2  # noqa: E402

from norfingen.config import settings  # noqa: E402

RENAMES = {
    "Advokatfirma Thommessen": "Advokatfirmaet Thommessen AS",
    "Nordic Insurance Partners AS": "Gjensidige Forsikring ASA",
}


def main() -> None:
    conn = psycopg2.connect(settings.DATABASE_URL)
    cur = conn.cursor()
    total = 0
    for old_name, new_name in RENAMES.items():
        cur.execute(
            "UPDATE vouchers SET description = REPLACE(description, %s, %s) "
            "WHERE description LIKE %s",
            (old_name, new_name, f"%{old_name}%"),
        )
        print(f"'{old_name}' -> '{new_name}': {cur.rowcount} voucherów zaktualizowanych")
        total += cur.rowcount
    conn.commit()
    print(f"Razem: {total} voucherów. Kwoty/konta/daty nietknięte.")
    conn.close()


if __name__ == "__main__":
    main()
