"""
Jednorazowa migracja: zapisuje metadane klientów i katalog usług z roster.py
do Supabase. Idempotentna — UPDATE/ON CONFLICT DO UPDATE, bezpieczna do
wielokrotnego uruchomienia.

Uwaga: seed_reference_data() (repository.py) robi to samo automatycznie przy
każdym starcie run_backfill.py/run_daily() — ten skrypt jest przydatny do
szybkiego, jednorazowego odświeżenia metadanych bez przechodzenia całego
seeda (departments/employees/accounts/vat_types/suppliers/products/projects).

Uruchomienie:
    python scripts/migrate_customer_metadata.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from norfingen.db.repository import get_connection  # noqa: E402
from norfingen.seed.roster import (  # noqa: E402
    CUSTOMER_NACE,
    CUSTOMER_PRICE_MULTIPLIER,
    CUSTOMERS,
    NORWEGIAN_POSTAL_CODES,
    SERVICES,
)


def migrate_customer_metadata() -> None:
    conn = get_connection()
    with conn.cursor() as cur:
        for customer in CUSTOMERS:
            nace = CUSTOMER_NACE[customer.number]
            cur.execute(
                """UPDATE customers
                   SET onboarding_date = %s,
                       churn_date = %s,
                       segment = %s,
                       price_multiplier = %s,
                       nace_code = %s,
                       nace_name = %s,
                       postal_code = %s
                   WHERE customer_number = %s""",
                (
                    customer.onboarding_date,
                    customer.churn_date,
                    customer.segment,
                    CUSTOMER_PRICE_MULTIPLIER[customer.number],
                    nace.code,
                    nace.name,
                    NORWEGIAN_POSTAL_CODES[customer.city],
                    customer.number,
                ),
            )

        for service in SERVICES:
            cur.execute(
                """INSERT INTO services (code, name, description, billing_model,
                                          availability, base_price_enterprise,
                                          base_price_mid, base_price_smb)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (code) DO UPDATE SET
                       name = EXCLUDED.name,
                       description = EXCLUDED.description,
                       billing_model = EXCLUDED.billing_model,
                       availability = EXCLUDED.availability,
                       base_price_enterprise = EXCLUDED.base_price_enterprise,
                       base_price_mid = EXCLUDED.base_price_mid,
                       base_price_smb = EXCLUDED.base_price_smb""",
                (
                    service.code, service.name, service.description,
                    service.billing_model.value, service.availability.value,
                    service.base_price_enterprise, service.base_price_mid, service.base_price_smb,
                ),
            )

    conn.commit()
    print(f"✓ Zmigrowano {len(CUSTOMERS)} klientów, {len(SERVICES)} usług")


if __name__ == "__main__":
    migrate_customer_metadata()
