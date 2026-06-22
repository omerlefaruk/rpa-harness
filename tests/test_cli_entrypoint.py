import subprocess
import sys


def test_python_module_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "harness.cli", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "RPA Harness" in result.stdout
    assert "--run-yaml" in result.stdout
