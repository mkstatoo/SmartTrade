"""Throw-away PostgreSQL cluster controlled by the tests themselves (initdb / pg_ctl), so deployment tests may stop it
hard, restart it and dump/restore databases without touching any shared server. Works as root (runs as `postgres`)."""
import glob
import os
import pwd
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path


def find_bin():
    for pat in sorted(glob.glob("/usr/lib/postgresql/*/bin"), reverse=True):
        if (Path(pat) / "initdb").exists():
            return Path(pat)
    p = shutil.which("initdb")
    return Path(p).parent if p else None


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Cluster:
    def __init__(self, bindir: Path):
        self.bin, self.port = bindir, free_port()
        self.base = Path(tempfile.mkdtemp(prefix="pgdeploy_"))
        self.root = os.geteuid() == 0
        if self.root:
            pw = pwd.getpwnam("postgres")
            os.chown(self.base, pw.pw_uid, pw.pw_gid)
        self.data, self.log = self.base / "data", self.base / "pg.log"

    def sh(self, cmd, check=True):
        full = ["su", "postgres", "-c", cmd] if self.root else ["sh", "-c", cmd]
        r = subprocess.run(full, capture_output=True, text=True)
        if check and r.returncode:
            raise RuntimeError(f"{cmd}\n{r.stdout}\n{r.stderr}")
        return r

    def init(self):
        self.sh(f"{self.bin}/initdb -D {self.data} -A trust -U postgres")
        return self

    def start(self):
        self.sh(f"{self.bin}/pg_ctl -D {self.data} -o '-p {self.port} -k {self.base}' -l {self.log} -w start")

    def stop(self, mode="fast"):
        self.sh(f"{self.bin}/pg_ctl -D {self.data} -m {mode} -w stop", check=False)

    def dsn(self, db="postgres"):
        return f"postgresql://postgres@/{db}?host={self.base}&port={self.port}"

    def create_db(self, name):
        self.sh(f"{self.bin}/createdb -h {self.base} -p {self.port} -U postgres {name}")
        return self.dsn(name)

    def drop_db(self, name):
        self.sh(f"{self.bin}/dropdb --force --if-exists -h {self.base} -p {self.port} -U postgres {name}", check=False)

    def dump(self, db, path):
        self.sh(f"{self.bin}/pg_dump -h {self.base} -p {self.port} -U postgres -Fc -f {path} {db}")

    def restore(self, db, path):
        self.sh(f"{self.bin}/pg_restore -h {self.base} -p {self.port} -U postgres --no-owner --exit-on-error -d {db} {path}")

    def log_text(self):
        return self.log.read_text(errors="replace") if self.log.exists() else ""

    def destroy(self):
        self.stop("immediate")
        shutil.rmtree(self.base, ignore_errors=True)
