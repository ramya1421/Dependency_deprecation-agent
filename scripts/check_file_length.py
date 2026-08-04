"""Fail if any given file exceeds CLAUDE.md's 300-line cap.

Ruff has no native rule for this (Pylint's C0302 "too-many-lines" is not
implemented in Ruff), so it's enforced here as a pre-commit hook instead.
"""

import sys

MAX_LINES = 300


def main(paths: list[str]) -> int:
    failed = False
    for path in paths:
        with open(path, encoding="utf-8") as f:
            n = sum(1 for _ in f)
        if n > MAX_LINES:
            print(f"{path}: {n} lines (max {MAX_LINES})")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
