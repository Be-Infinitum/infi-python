"""Runs the examples in sequence and prints ✓/✗ per script."""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

here = Path(__file__).resolve().parent
scripts = sorted(p.name for p in here.iterdir() if re.fullmatch(r"\d\d_.*\.py", p.name))
results = []

for name in scripts:
    print(f"\n════════ {name} ════════", flush=True)
    started = time.time()
    code = subprocess.call([sys.executable, str(here / name)])
    results.append((name, code == 0, round(time.time() - started)))

print("\n════════ Summary ════════")
for name, ok, seconds in results:
    print(f"{'✓' if ok else '✗'} {name} ({seconds}s)")
failed = sum(1 for _, ok, _ in results if not ok)
print(f"\n{len(results) - failed}/{len(results)} scripts ok")
sys.exit(0 if failed == 0 else 1)
