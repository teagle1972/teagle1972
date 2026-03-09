from __future__ import annotations

import argparse
from pathlib import Path
import sys


DEFAULT_GLOBS = ("*.py", "*.md", "*.txt", "*.json", "*.yaml", "*.yml")

# High-confidence mojibake fragments seen in this codebase.
MOJIBAKE_TOKENS = (
    "寮€",
    "缁撴潫",
    "澶勭悊",
    "鍒ゆ柇",
    "杈撳叆",
    "鏉′欢",
)


def iter_files(root: Path, globs: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for pattern in globs:
        files.extend(root.rglob(pattern))
    return sorted({p for p in files if p.is_file()})


def find_issues(path: Path, text: str) -> list[str]:
    issues: list[str] = []
    lines = text.splitlines()
    skip_token_scan = path.name == "check_text_integrity.py"
    for lineno, line in enumerate(lines, start=1):
        if "\ufffd" in line:
            issues.append(f"{path}:{lineno}: contains replacement char U+FFFD")
        if not skip_token_scan:
            for token in MOJIBAKE_TOKENS:
                if token in line:
                    issues.append(f"{path}:{lineno}: suspicious mojibake token '{token}'")
                    break
    return issues


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Check repository text files for encoding/mojibake issues.")
    parser.add_argument("--root", default=".", help="Repository root path")
    parser.add_argument("--strict-utf8", action="store_true", help="Fail when a text file cannot decode as utf-8")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    files = iter_files(root, DEFAULT_GLOBS)
    all_issues: list[str] = []

    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            if args.strict_utf8:
                all_issues.append(f"{path}: cannot decode as utf-8")
            continue
        all_issues.extend(find_issues(path, text))

    if all_issues:
        print("[text-integrity] FAILED")
        for issue in all_issues:
            print(issue)
        return 1

    print(f"[text-integrity] OK ({len(files)} files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
