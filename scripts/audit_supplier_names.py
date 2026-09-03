"""
scripts/audit_supplier_names.py

Sprawdza każdego dostawcę z roster.SUPPLIERS względem publicznego API
Brønnøysundregistrene (rejestr podmiotów, data.brreg.no). W PRZECIWIEŃSTWIE
do (nieistniejącego w tym repo — sprawdzone, brak śladu w SESSION_HANDOFF.md)
hipotetycznego audytu klientów, tu DOPASOWANIE do realnej firmy jest
POŻĄDANYM wynikiem: fikcyjna firma NorFinGen realistycznie płaci prawdziwym,
dużym dostawcom (Microsoft, Telenor itp.) — standardowa praktyka w modelach
symulacyjnych, nie ryzyko.

Uruchomienie:
    python scripts/audit_supplier_names.py

Zewnętrzne API — publiczne, bez klucza, tylko odczyt (GET), 0.5s opóźnienia
między zapytaniami (uprzejmość wobec publicznego rejestru rządowego).
"""

import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

BRREG_SEARCH_URL = "https://data.brreg.no/enhetsregisteret/api/enheter"


def find_real_entity(company_name: str) -> list[dict]:
    response = requests.get(
        BRREG_SEARCH_URL,
        params={"navn": company_name, "size": 5},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("_embedded", {}).get("enheter", [])


def audit_suppliers(supplier_names: list[str]) -> dict:
    results = {}
    for name in supplier_names:
        matches = find_real_entity(name)
        exact = [e for e in matches
                 if e.get("navn", "").strip().lower() == name.strip().lower()]
        close = [e for e in matches
                 if name.strip().lower() in e.get("navn", "").strip().lower()
                 or e.get("navn", "").strip().lower() in name.strip().lower()]
        results[name] = {
            "exact_match": exact[0] if exact else None,
            "close_matches": close,
        }
        time.sleep(0.5)
    return results


if __name__ == "__main__":
    from norfingen.seed.roster import SUPPLIERS  # noqa: E402

    names = [s.name for s in SUPPLIERS]  # SupplierSeed to dataclass, nie dict
    results = audit_suppliers(names)
    for name, info in results.items():
        if info["exact_match"]:
            org = info["exact_match"].get("organisasjonsnummer")
            addr = info["exact_match"].get("forretningsadresse", {}).get("poststed", "?")
            print(f"OK - '{name}' matches real entity: org.nr {org}, {addr}")
        elif info["close_matches"]:
            print(f"CZESCIOWE DOPASOWANIE dla '{name}':")
            for m in info["close_matches"][:3]:
                print(f"   -> '{m.get('navn')}' (org.nr {m.get('organisasjonsnummer')})")
        else:
            print(f"BRAK DOPASOWANIA - '{name}' nie znaleziono w Brreg jako taki")
