#!/usr/bin/env python3
"""Independent PostgreSQL verification: boots its OWN throw-away PostgreSQL cluster (no Docker, no pre-existing server),
runs the full PG-backed test-suite verbosely and writes the raw output to docs/PG_EVIDENCE.txt.

    python scripts/pg_verify.py            # uses initdb/pg_ctl found under /usr/lib/postgresql/*/bin or PATH
"""
import glob
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.getenv("PG_VERIFY_PORT", "5599"))


def find_bin() -> Path:
    for pat in sorted(glob.glob("/usr/lib/postgresql/*/bin"), reverse=True):
        if (Path(pat) / "initdb").exists():
            return Path(pat)
    p = shutil.which("initdb")
    if p:
        return Path(p).parent
    sys.exit("initdb not found: install postgresql-16")


def main() -> int:
    bindir = find_bin()
    root = os.geteuid() == 0
    base = Path(tempfile.mkdtemp(prefix="pgverify_"))
    if root:
        pw = pwd.getpwnam("postgres")
        os.chown(base, pw.pw_uid, pw.pw_gid)
    data, sock = base / "data", base
    run_as = ["su", "postgres", "-c"] if root else None

    def sh(cmd: str, check=True):
        full = run_as + [cmd] if run_as else ["sh", "-c", cmd]
        return subprocess.run(full, capture_output=True, text=True, check=check)

    lines = []
    try:
        sh(f"{bindir}/initdb -D {data} -A trust -U postgres")
        sh(f"{bindir}/pg_ctl -D {data} -o '-p {PORT} -k {sock}' -l {base}/pg.log -w start")
        dsn = f"postgresql://postgres@/postgres?host={sock}&port={PORT}"
        ver = sh(f"{bindir}/psql 'postgresql://postgres@/postgres?host={sock}&port={PORT}' -Atc 'select version()'").stdout.strip()
        lines += ["# PostgreSQL verification evidence (raw output)", f"date_utc: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}",
                  f"server: {ver}", f"python: {sys.version.split()[0]}", ""]
        env = {**os.environ, "TEST_DATABASE_URL": dsn}
        for title, args in [("migrations: fresh DB, run twice", None),
                            ("pytest -v PostgreSQL-specific suites (migrations, DB failures, chain ingestion, deployment/crash/restore)", ["-v", "-p", "no:cacheprovider",
                              "tests/test_postgres.py", "tests/test_db_failures.py", "tests/test_chain_ingest.py", "tests/test_deploy.py",
                              "tests/test_paper_cycle.py", "tests/test_time_exit_and_ids.py"]),
                            ("pytest -q (whole suite, no skips allowed)", ["-q", "-rs", "-p", "no:cacheprovider"])]:
            lines.append(f"\n===== {title} =====")
            if args is None:
                import psycopg
                from psycopg.conninfo import make_conninfo
                with psycopg.connect(dsn, autocommit=True) as c:
                    c.execute('CREATE DATABASE "evidence"')
                edsn = make_conninfo(dsn, dbname="evidence")
                for i in (1, 2):
                    r = subprocess.run([sys.executable, "-m", "app.migrate"], cwd=ROOT, env={**env, "DATABASE_URL": edsn},
                                       capture_output=True, text=True)
                    lines.append(f"run {i}: rc={r.returncode} {r.stdout.strip()} {r.stderr.strip()}")
                continue
            r = subprocess.run([sys.executable, "-m", "pytest", *args], cwd=ROOT, env=env, capture_output=True, text=True)
            lines.append(r.stdout.strip())
            lines.append(f"exit code: {r.returncode}")
            if r.returncode:
                break
        ok = all("exit code: 0" in l or not l.startswith("exit code") for l in lines)
        lines.append("\nRESULT: " + ("PASS" if ok and "skipped" not in "\n".join(lines[-3:]).lower() else "FAIL"))
    finally:
        sh(f"{bindir}/pg_ctl -D {data} -m fast stop", check=False)
        shutil.rmtree(base, ignore_errors=True)
    out = ROOT / "docs" / "PG_EVIDENCE.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-6:]))
    return 0 if lines[-1].endswith("PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
