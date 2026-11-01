"""Guard: generators must stay deterministic (docs/SPEC_poprawki_ksiegowe.md, phase 0.5).

Every random draw must come from a local `random.Random(<seed>)`. Forbidden in src/:
* module-level `random.<fn>()` (global stream - result depends on call order),
* the built-in `hash()` (salted per process for str),
* wall-clock reads (`datetime.now/utcnow/today`, `time.time`) that would make output depend on when it runs.

`date.today()` is allowed only at the explicit allowlist below: the single source of "today"
(seed/payroll.get_generation_cutoff_date). The supplier-invoice PAID heuristic that used to
be the second entry is gone (phase 0.5b: status follows the payments).
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

# (relative path, number of allowed `date.today()` calls)
DATE_TODAY_ALLOWLIST = {
    "norfingen/seed/payroll.py": 1,  # get_generation_cutoff_date() - the single source of "today"
}

GLOBAL_RANDOM_FUNCS = {
    "random", "uniform", "randint", "randrange", "choice", "choices", "sample", "shuffle",
    "gauss", "normalvariate", "seed", "getrandbits", "triangular", "betavariate",
}
WALL_CLOCK = {("datetime", "now"), ("datetime", "utcnow"), ("datetime", "today"), ("time", "time")}


def _calls(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def _src_files():
    return [p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts]


def test_no_global_random_stream():
    offenders = []
    for path in _src_files():
        for call in _calls(path):
            f = call.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "random":
                if f.attr in GLOBAL_RANDOM_FUNCS:
                    offenders.append(f"{path.relative_to(SRC)}:{call.lineno} random.{f.attr}()")
    assert not offenders, "global random stream used: " + "; ".join(offenders)


def test_no_builtin_hash():
    offenders = [
        f"{path.relative_to(SRC)}:{call.lineno}"
        for path in _src_files() for call in _calls(path)
        if isinstance(call.func, ast.Name) and call.func.id == "hash"
    ]
    assert not offenders, "built-in hash() is process-salted: " + "; ".join(offenders)


def test_no_wall_clock_outside_allowlist():
    offenders = []
    for path in _src_files():
        rel = str(path.relative_to(SRC))
        today_calls = 0
        for call in _calls(path):
            f = call.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                if (f.value.id, f.attr) in WALL_CLOCK:
                    offenders.append(f"{rel}:{call.lineno} {f.value.id}.{f.attr}()")
                if f.value.id == "date" and f.attr == "today":
                    today_calls += 1
        if today_calls > DATE_TODAY_ALLOWLIST.get(rel, 0):
            offenders.append(f"{rel}: {today_calls} date.today() call(s), allowed {DATE_TODAY_ALLOWLIST.get(rel, 0)}")
    assert not offenders, "wall-clock dependence: " + "; ".join(offenders)
