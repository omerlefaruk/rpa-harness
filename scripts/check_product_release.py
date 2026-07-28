"""Clean-checkout release smoke checks used by CI and package qualification."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    manifest = json.loads((ROOT / "packages/rpa-harness-agent/package.json").read_text())
    if manifest["version"] != "0.1.0":
        raise SystemExit("Python and npm release versions must match")
    required = [ROOT / "pyproject.toml", ROOT / "uv.lock", ROOT / "harness/mcp_server.py"]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise SystemExit(f"release assets missing: {', '.join(missing)}")
    subprocess.run([sys.executable, "-m", "compileall", "-q", "harness", "main.py"], cwd=ROOT, check=True)
    print(json.dumps({"ok": True, "python_version": manifest["version"], "npm_version": manifest["version"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
