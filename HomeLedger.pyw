"""Double-click launcher (the .pyw extension means no black console window on Windows)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from homeledger.main import run  # noqa: E402

if __name__ == "__main__":
    sys.exit(run())
