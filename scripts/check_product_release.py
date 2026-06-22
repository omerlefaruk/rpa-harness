from __future__ import annotations

import subprocess
import sys
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("npm not found")
    run([sys.executable, "-m", "pytest", "tests/test_cli_entrypoint.py", "tests/test_product_init.py", "-q"])
    run([npm, "test"], ROOT / "packages" / "rpa-harness-agent")
    run([npm, "pack", "--dry-run"], ROOT / "packages" / "rpa-harness-agent")
    python = ["py", "-3"] if sys.platform == "win32" and shutil.which("py") else [sys.executable]
    run([*python, "-m", "pip", "wheel", ".", "--no-deps", "-w", ".pytest_tmp/wheels"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
