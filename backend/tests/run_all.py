"""
Runs every test file in this folder (test_accounts, test_reports, test_places, test_content, test_ops), each in its own
process, and says which ones failed. A new test_*.py file is picked up by its name.

    py tests/run_all.py

Each file sets up its own temporary database before the app is loaded, so they cannot share one
process (running them all in one `pytest` process fails on the accounts the files create). Each
file also runs on its own: `py tests/test_places.py`.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    failed = []
    for path in sorted(HERE.glob("test_*.py")):
        print(f"\n=== {path.name} ===", flush=True)
        if subprocess.run([sys.executable, str(path)]).returncode != 0:
            failed.append(path.name)
    print()
    if failed:
        print("FAILED: " + ", ".join(failed))
        return 1
    print("All test files passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
