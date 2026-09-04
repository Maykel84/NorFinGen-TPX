"""Wspólny wzorzec paginacji list: limit/offset, domyślny 100, max 1000."""

from fastapi import Query

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000


def pagination_params(
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Max wierszy (≤1000)"),
    offset: int = Query(default=0, ge=0, description="Liczba wierszy do pominięcia"),
) -> tuple[int, int]:
    return limit, offset
