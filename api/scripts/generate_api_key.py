"""Generuje nowy klucz API dla usługi `api/` i zapisuje jego hash w `api_keys`.

Uruchamiane z uprawnieniami właściciela (`DATABASE_URL`, jak pozostałe skrypty
administracyjne w `scripts/`) - NIE przez `api_key_manager` (ta rola tylko
odczytuje/aktualizuje istniejące wiersze podczas walidacji zapytań, nie
tworzy nowych kluczy). Surowy klucz istnieje tylko w tym wywołaniu (stdout),
w bazie zapisywany jest wyłącznie jego SHA-256.

Użycie:
    python api/scripts/generate_api_key.py "Nazwa właściciela klucza" [rate_limit_per_hour]

Przykład:
    python api/scripts/generate_api_key.py "demo-curl-test" 100
"""

import hashlib
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from norfingen.db.repository import get_connection  # noqa: E402


def generate_api_key(owner_label: str, rate_limit: int = 100) -> str:
    raw_key = f"nfg_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO api_keys (key_hash, owner_label, rate_limit_per_hour)
            VALUES (%s, %s, %s)
            """,
            (key_hash, owner_label, rate_limit),
        )
    conn.commit()
    conn.close()

    print(f"Nowy klucz API dla '{owner_label}' (rate limit {rate_limit}/h).")
    print("Zapisz TERAZ - nie pokaże się ponownie (baza trzyma tylko hash):")
    print(raw_key)
    return raw_key


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Użycie: python api/scripts/generate_api_key.py <owner_label> [rate_limit_per_hour]")
        sys.exit(1)
    label = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    generate_api_key(label, limit)
