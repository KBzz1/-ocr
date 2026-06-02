#!/usr/bin/env python3
"""Check dev entry scripts resolve ROOT_DIR to the repository root."""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEV_SCRIPTS = (
    PROJECT_ROOT / "scripts/dev/run.sh",
    PROJECT_ROOT / "scripts/dev/stop.sh",
)
ROOT_DIR_PATTERN = re.compile(
    r'^ROOT_DIR="\$\(cd "\$\(dirname "\$\{BASH_SOURCE\[0\]\}"\)/\.\./\.\." && pwd\)"$',
    re.MULTILINE,
)


def main() -> int:
    failures: list[str] = []
    for script in DEV_SCRIPTS:
        content = script.read_text(encoding="utf-8")
        if not ROOT_DIR_PATTERN.search(content):
            failures.append(str(script.relative_to(PROJECT_ROOT)))

    if failures:
        print("DEV_SCRIPT_ROOT_CHECK_FAILED: " + ", ".join(failures))
        return 1

    print("DEV_SCRIPT_ROOT_CHECK_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
