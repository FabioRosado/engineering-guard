import os
import subprocess
import sys
from pathlib import Path


root = Path(__file__).resolve().parent
for module in ("before", "fixed"):
    result = subprocess.run(
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", str(root), "-p", "test_startup.py"],
        cwd=root,
        capture_output=True,
        text=True,
        env={**os.environ, "STARTUP_EXAMPLE": module},
    )
    if module == "before":
        expected_failures = (
            "FAIL: test_closes_connection_on_failed_initialization",
            "FAIL: test_preserves_startup_and_cleanup_errors",
        )
        if result.returncode == 0 or not all(failure in result.stderr for failure in expected_failures):
            raise SystemExit("Baseline did not fail for the expected reasons:\n" + result.stderr)
    elif result.returncode != 0:
        raise SystemExit("Corrected example failed:\n" + result.stderr)
    print(f"{module}: {'expected cleanup failures' if module == 'before' else 'all tests passed'}")
