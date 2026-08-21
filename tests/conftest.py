from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
    ROOT / "skills" / "empirical-macro" / "src",
    ROOT / "skills" / "macro-data" / "src",
)

for source in SOURCE_ROOTS:
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
