#!/usr/bin/env python3
"""One-click local bootstrap for PyCharm.

Run this file directly from PyCharm (green ▶ button).
It installs dependencies, prepares `.env` and data directory,
and runs Alembic migrations.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_EXAMPLE = ROOT / ".env.example"
ENV_FILE = ROOT / ".env"
DATA_DIR = ROOT / "data"


def _print_step(message: str) -> None:
    print(f"\n=== {message} ===")


def _run(cmd: list[str], env: dict[str, str] | None = None, required: bool = True) -> bool:
    print("$", " ".join(cmd))
    completed = subprocess.run(cmd, cwd=ROOT, env=env, check=False)
    if completed.returncode != 0:
        if required:
            raise subprocess.CalledProcessError(completed.returncode, cmd)
        print(f"Warning: command failed with exit code {completed.returncode}")
        return False
    return True


def _load_dotenv(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _resolve_database_url(env_from_dotenv: dict[str, str]) -> str:
    """Return database URL used during bootstrap migrations.

    Bootstrap should be deterministic and not depend on a running Postgres instance
    or credentials from a user-edited .env file. To opt in to DATABASE_URL from .env,
    set BOOTSTRAP_USE_ENV_DATABASE=1.
    """

    if env_from_dotenv.get("BOOTSTRAP_USE_ENV_DATABASE") == "1":
        return env_from_dotenv.get("DATABASE_URL", "sqlite:///data/app.db")
    return "sqlite:///data/app.db"


def main() -> int:
    _print_step("Bootstrap start")
    print(f"Python: {sys.executable}")
    print(f"Project: {ROOT}")

    _print_step("Create data directory")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"OK: {DATA_DIR}")

    _print_step("Prepare .env")
    if not ENV_FILE.exists() and ENV_EXAMPLE.exists():
        ENV_FILE.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        print("Created .env from .env.example")
    elif ENV_FILE.exists():
        print(".env already exists (left unchanged)")
    else:
        print("Warning: .env.example not found")

    _print_step("Install Python dependencies")
    _run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    _run([sys.executable, "-m", "pip", "install", "python-dotenv"], required=False)

    _print_step("Run database migrations")
    env = os.environ.copy()
    env_from_dotenv = _load_dotenv(ENV_FILE)
    env.update(env_from_dotenv)
    env["PYTHONPATH"] = str(ROOT)
    env["DATABASE_URL"] = _resolve_database_url(env_from_dotenv)
    if env["DATABASE_URL"].startswith("sqlite"):
        print("Using SQLite database for bootstrap migrations.")
    _run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env)

    _print_step("Done")
    print("Aplikacja gotowa. Uruchom teraz app.py w PyCharm.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
