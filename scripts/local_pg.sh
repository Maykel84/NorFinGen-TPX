#!/bin/bash
# A throw-away PostgreSQL for regenerating the history locally - never production.
#
#   scripts/local_pg.sh start     # create (first time) and start it on 127.0.0.1:54329
#   scripts/local_pg.sh stop
#   scripts/local_pg.sh url       # prints the DATABASE_URL to use with local_regen.sh / the tests
#
# Data lives in .local/pg (git-ignored), so it survives a cleaned scratch directory. It uses the
# Postgres.app binaries; the app's own server is not touched (its permission prompt for "trust"
# connections is a setting of yours, not something to bypass - this is a separate instance).
# fsync is off on purpose: the database is disposable and a full regeneration is ~30x faster.
set -euo pipefail

BIN="${PG_BIN:-/Applications/Postgres.app/Contents/Versions/latest/bin}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)/.local/pg"
SOCK=/tmp/nfgpgsock            # unix-socket paths are limited to ~100 bytes, so keep it short
PORT=54329
DB=norfingen_local

case "${1:-}" in
  start)
    mkdir -p "$SOCK" "$ROOT"
    if [ ! -d "$ROOT/data" ]; then
      "$BIN/initdb" -D "$ROOT/data" -U norfingen --auth=trust -E UTF8 >/dev/null
    fi
    if ! "$BIN/pg_isready" -h 127.0.0.1 -p $PORT >/dev/null 2>&1; then
      "$BIN/pg_ctl" -D "$ROOT/data" -l "$ROOT/server.log" \
        -o "-p $PORT -k $SOCK -c listen_addresses=127.0.0.1 -c fsync=off -c synchronous_commit=off -c full_page_writes=off" start >/dev/null
      sleep 2
    fi
    "$BIN/psql" -h 127.0.0.1 -p $PORT -U norfingen -d postgres -Atc \
      "SELECT 1 FROM pg_database WHERE datname='$DB'" | grep -q 1 || \
      "$BIN/psql" -h 127.0.0.1 -p $PORT -U norfingen -d postgres -qc "CREATE DATABASE $DB"
    echo "local Postgres ready: postgresql://norfingen@127.0.0.1:$PORT/$DB"
    ;;
  stop)
    "$BIN/pg_ctl" -D "$ROOT/data" stop
    ;;
  url)
    echo "postgresql://norfingen@127.0.0.1:$PORT/$DB"
    ;;
  *)
    echo "usage: $0 start|stop|url" >&2; exit 2;;
esac
