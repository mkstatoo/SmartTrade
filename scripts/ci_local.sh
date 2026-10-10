#!/usr/bin/env bash
# Emulates .github/workflows/tests.yml steps against a local PostgreSQL 16 (no Docker needed).
# Usage: TEST_DATABASE_URL=postgresql://user@/postgres?host=/path&port=5432 scripts/ci_local.sh
set -euo pipefail
cd "$(dirname "$0")/.."
: "${TEST_DATABASE_URL:?set TEST_DATABASE_URL}"
python - <<'PY'
import os, uuid, psycopg
from psycopg.conninfo import make_conninfo
name = "ci_" + uuid.uuid4().hex[:8]
with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as c:
    c.execute(f'CREATE DATABASE "{name}"')
open("/tmp/ci_db_name", "w").write(make_conninfo(os.environ["TEST_DATABASE_URL"], dbname=name))
PY
export DATABASE_URL="$(cat /tmp/ci_db_name)"
python -m app.migrate
python -m app.migrate | grep -q "nothing (already up to date)"
python -m pytest -q -rs | tee /tmp/pytest.out
! grep -qi "skipped" /tmp/pytest.out
echo "CI-LOCAL OK"
