"""Regresja incydentu Fazy 7 (SESSION_HANDOFF.md p.13i) — konto 7790 użyte w
company_events.py nigdy nie trafiło do repository.ACCOUNTS_SEED, więc backfill
na żywej bazie wywalił się ForeignKeyViolation przy pierwszym UNPROFITABLE_QUARTER.
Offline sanity-check tego nie złapał, bo nie dotyka prawdziwej bazy/FK.

Ten test sprawdza WYŁĄCZNIE numery kont wystawione jako moduł-level stałe
ACCOUNT_* w generators/*.py (konwencja tego repo) — nie łapie kont zaszytych
bezpośrednio jako literały (np. acct(2000) w voucher.py), ale to dokładnie
klasa błędu, którą złapał ten incydent."""

import importlib
import pkgutil

from norfingen.db.repository import ACCOUNTS_SEED
from norfingen.generators import __path__ as generators_path

SEEDED_ACCOUNT_NUMBERS = {number for number, *_ in ACCOUNTS_SEED}


def _discover_account_constants() -> dict[str, int]:
    found: dict[str, int] = {}
    for module_info in pkgutil.iter_modules(generators_path):
        module = importlib.import_module(f"norfingen.generators.{module_info.name}")
        for name, value in vars(module).items():
            if name.startswith("ACCOUNT_") and isinstance(value, int):
                found[f"{module_info.name}.{name}"] = value
    return found


def test_every_account_constant_is_in_accounts_seed():
    constants = _discover_account_constants()
    assert len(constants) > 5  # sanity — upewnia się, że discovery faktycznie coś znalazło

    missing = {qualname: number for qualname, number in constants.items() if number not in SEEDED_ACCOUNT_NUMBERS}
    assert not missing, f"Konta użyte w generatorach, ale nieobecne w ACCOUNTS_SEED (spowoduje ForeignKeyViolation na żywej bazie): {missing}"
