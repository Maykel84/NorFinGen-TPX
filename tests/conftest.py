"""Safety net: no unit test may reach a real database through DATABASE_URL.

`norfingen.config.settings.DATABASE_URL` is read from `.env` - on this machine that is PRODUCTION. A test that forgets
to patch a repository function would otherwise open a connection to it. That nearly happened in phase 4: new repository
functions were not yet in the tests' mocks, and the first unpatched call went to Supabase (it failed on a missing table
before anything was written, but only by luck). From here every test sees an address that refuses connections, so a
forgotten mock fails instantly and harmlessly instead of touching production.

Tests that DO need a database use their own variable, NORFINGEN_TEST_PG_URL (a local scratch Postgres), and connect
with it explicitly - they never go through `settings`.
"""

from norfingen.config import settings

UNREACHABLE = "postgresql://tests-never-touch-a-database@127.0.0.1:1/none"
settings.DATABASE_URL = UNREACHABLE

from norfingen.db import repository  # noqa: E402

repository._conn = None  # drop any connection cached before this module ran
