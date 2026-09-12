"""Install the declared MCP floor and run the suite against that installed package.

Run from a source checkout: python tools/check_mcp_floor.py
The environment and installed build are disposable; this never edits the checkout.
"""

import os
import re
import subprocess
import tempfile
import venv
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    # Read the actual declaration, not a second manually maintained floor pin.
    matches = re.findall(r'^\s*"mcp>=(\d+\.\d+\.\d+),<2",\s*$',
                         (root / "pyproject.toml").read_text(), re.MULTILINE)
    if len(matches) != 1:
        raise SystemExit("Cannot identify exactly one declared mcp>=X.Y.Z,<2 requirement")
    floor = matches[0]
    with tempfile.TemporaryDirectory(prefix="telos-mcp-floor-") as scratch:
        directory = Path(scratch)
        environment = directory / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        env = {**os.environ, "TELOS_MCP_TEST_FLOOR": "1", "PYTHONPATH": "",
               "TELOS_MCP_ENGINE": "stub", "PYTHONDONTWRITEBYTECODE": "1"}
        for args in (
            ["-m", "pip", "install", f"{root}[dev]", f"mcp=={floor}"],
            ["-m", "pip", "check"],
            ["-m", "pytest", "--import-mode=importlib", "-p", "no:cacheprovider",
             str(root / "tests"), "-q"],
        ):
            subprocess.run([str(python), *args], cwd=directory, env=env, check=True)
        print(f"DECLARED_FLOOR_PASS mcp=={floor}")


if __name__ == "__main__":
    main()
