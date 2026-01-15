#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-3.0-or-later

"""Validate SPDX copyright headers on new and modified files.

This script is designed to run in CI (e.g. GitHub Actions) and compare the
current HEAD against a base revision to ensure SPDX headers are present and
up-to-date.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import fnmatch
import pathlib
import re
import subprocess
import sys
from typing import Iterable, List, Optional, Sequence, Tuple

CURRENT_YEAR = _dt.datetime.now(_dt.UTC).year
COMMENT_PREFIXES = ("//", "#")
HEADER_REGEX = re.compile(
    r"^(?P<prefix>//|#)\s*SPDX-FileCopyrightText:\s*"
    r"(?P<years>\d{4}(?:-\d{4})?)\s+"
    r"UnionTech Software Technology Co\., Ltd\.?\s*$"
)
LICENSE_REGEX = re.compile(
    r"^(?P<prefix>//|#)\s*SPDX-License-Identifier:\s*(?P<license>\S.*)$"
)


class Violation:
    """Container for reporting validation problems."""

    def __init__(self, path: str, message_en: str, message_zh: str) -> None:
        self.path = path
        self.message_en = message_en
        self.message_zh = message_zh

    def __str__(self) -> str:
        return f"[{self.path}] {self.message_en}\n{self.message_zh}"


def run_git(args: Sequence[str]) -> str:
    """Execute a git command and return its stdout as text."""

    result = subprocess.run(
        ["git", *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed with exit code {result.returncode}:\n{result.stdout}"
        )
    return result.stdout


def list_changed_files(base: str) -> List[Tuple[str, str]]:
    """Return a list of (status, path) for files changed since base."""

    diff_output = run_git(["diff", "--name-status", f"{base}...HEAD", "--diff-filter=ACMR"])
    entries: List[Tuple[str, str]] = []
    for line in diff_output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") or status.startswith("C"):
            # Use the destination path for renames/copies: columns are status, source, dest.
            if len(parts) >= 3:
                entries.append((status[:1], parts[2]))
            continue
        if len(parts) >= 2:
            entries.append((status, parts[1]))
    return entries


def extract_header_lines(path: pathlib.Path) -> Tuple[Optional[str], Optional[str]]:
    """Return the SPDX header and license lines if present within the first 10 lines."""

    try:
        with path.open("r", encoding="utf-8") as handle:
            lines = [handle.readline() for _ in range(10)]
    except FileNotFoundError:
        return None, None
    except UnicodeDecodeError:
        return None, None

    header_line = None
    license_line = None
    for raw_line in lines:
        if not raw_line:
            break
        line = raw_line.strip("\ufeff\n\r")
        if not line.strip():
            continue
        if header_line is None and HEADER_REGEX.match(line):
            header_line = line
            continue
        if header_line and license_line is None and LICENSE_REGEX.match(line):
            license_line = line
            break
    return header_line, license_line


def get_creation_year(path: str) -> Optional[int]:
    """Return the creation year for a tracked file, if known."""

    try:
        output = run_git(
            [
                "log",
                "--diff-filter=A",
                "--follow",
                "--format=%ad",
                "--date=format:%Y",
                path,
            ]
        )
    except RuntimeError:
        return None

    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return None
    # Oldest commit is last in the list when using default ordering.
    return int(lines[-1])


def parse_years(year_field: str) -> Tuple[int, Optional[int]]:
    """Split a SPDX year field into start and end years."""

    if "-" in year_field:
        start, end = year_field.split("-", 1)
        return int(start), int(end)
    return int(year_field), None


def validate_new_file(
    path: str,
    years_field: Optional[str],
    license_ok: bool,
    violations: List[Violation],
) -> None:
    if years_field is None:
        violations.append(
            Violation(
                path,
                "Missing SPDX header on new file. Expected current year header.",
                "新增文件缺少 SPDX 版权头，需添加包含当前年份的版权信息。",
            )
        )
        return

    start_year, end_year = parse_years(years_field)
    if end_year is not None:
        violations.append(
            Violation(
                path,
                "New files must use a single year (no range) in the SPDX header.",
                "新增文件的 SPDX 版权头必须只包含当前年份，不能使用年份范围。",
            )
        )
    elif start_year != CURRENT_YEAR:
        violations.append(
            Violation(
                path,
                f"SPDX header year should be {CURRENT_YEAR} for new files.",
                f"新增文件的 SPDX 版权年份应为 {CURRENT_YEAR}。",
            )
        )
    if not license_ok:
        violations.append(
            Violation(
                path,
                "Missing SPDX license identifier line below the copyright header.",
                "缺少 SPDX-License-Identifier 行，请紧跟在版权头下方添加。",
            )
        )


def validate_modified_file(
    path: str,
    years_field: Optional[str],
    license_ok: bool,
    creation_year: Optional[int],
    violations: List[Violation],
) -> None:
    if years_field is None:
        violations.append(
            Violation(
                path,
                "Missing SPDX header on modified file.",
                "被修改的文件缺少 SPDX 版权头。",
            )
        )
        return

    start_year, end_year = parse_years(years_field)
    if end_year is None:
        if start_year != CURRENT_YEAR:
            if creation_year and creation_year < CURRENT_YEAR:
                range_text = f"{creation_year}-{CURRENT_YEAR}"
                violations.append(
                    Violation(
                        path,
                        (
                            "File predates current year; update SPDX header to use a year range "
                            f"{range_text}."
                        ),
                        (
                            "文件创建年份早于当前年份，请将 SPDX 版权头更新为年份范围 "
                            f"{range_text}。"
                        ),
                    )
                )
            else:
                violations.append(
                    Violation(
                        path,
                        f"SPDX header year should be {CURRENT_YEAR}.",
                        f"请将 SPDX 版权年份更新为 {CURRENT_YEAR}。",
                    )
                )
        elif creation_year and creation_year < CURRENT_YEAR:
            violations.append(
                Violation(
                    path,
                    (
                        "File has earlier creation year; use range format "
                        f"{creation_year}-{CURRENT_YEAR}."
                    ),
                    (
                        "该文件创建于较早年份，应使用年份范围格式 "
                        f"{creation_year}-{CURRENT_YEAR}。"
                    ),
                )
            )
    else:
        if start_year > end_year:
            violations.append(
                Violation(
                    path,
                    "Invalid SPDX year range (start year greater than end year).",
                    "SPDX 年份范围不合法：起始年份大于结束年份。",
                )
            )
        if end_year != CURRENT_YEAR:
            violations.append(
                Violation(
                    path,
                    f"Update SPDX year range end to {CURRENT_YEAR}.",
                    f"请将 SPDX 年份范围的结束年份更新为 {CURRENT_YEAR}。",
                )
            )
        if creation_year and start_year != creation_year:
            violations.append(
                Violation(
                    path,
                    (
                        f"Year range should start at the file creation year {creation_year}."
                    ),
                    (
                        f"年份范围应以文件创建年份 {creation_year} 开始。"
                    ),
                )
            )
        if start_year == end_year:
            violations.append(
                Violation(
                    path,
                    "Year range uses identical start and end; use single year format instead.",
                    "年份范围的起止相同，应改为单年份格式。",
                )
            )
    if not license_ok:
        violations.append(
            Violation(
                path,
                "Missing SPDX license identifier line below the copyright header.",
                "缺少 SPDX-License-Identifier 行，请紧跟在版权头下方添加。",
            )
        )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate SPDX headers on changed files")
    parser.add_argument(
        "--base",
        default=os.environ.get("GITHUB_BASE_REF", "origin/main"),
        help="Base reference to diff against (default: environment GITHUB_BASE_REF or origin/main)",
    )
    parser.add_argument(
        "--include",
        nargs="*",
        help="Optional list of glob patterns (relative) to include. Defaults to all changed files.",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        help="Optional list of glob patterns (relative) to exclude from validation.",
    )
    args = parser.parse_args(argv)

    base_ref = args.base

    try:
        run_git(["rev-parse", base_ref])
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 2

    changed = list_changed_files(base_ref)
    if not changed:
        print("No applicable file changes detected; skipping SPDX validation.")
        return 0

    include_patterns = [pattern for pattern in args.include or []]
    exclude_patterns = [pattern for pattern in args.exclude or []]

    violations: List[Violation] = []

    for status, rel_path in changed:
        path_obj = pathlib.Path(rel_path)
        path_posix = pathlib.PurePosixPath(rel_path)
        if include_patterns and not any(fnmatch.fnmatch(path_posix.as_posix(), pattern) for pattern in include_patterns):
            continue
        if exclude_patterns and any(fnmatch.fnmatch(path_posix.as_posix(), pattern) for pattern in exclude_patterns):
            continue
        if path_obj.is_dir():
            continue

        header_line, license_line = extract_header_lines(path_obj)
        years_field: Optional[str] = None
        license_ok = False

        if header_line:
            header_match = HEADER_REGEX.match(header_line.strip())
            if header_match:
                years_field = header_match.group("years")
                header_prefix = header_match.group("prefix")
            else:
                violations.append(
                    Violation(
                        rel_path,
                        "SPDX header format is invalid.",
                        "SPDX 版权头格式不符合要求。",
                    )
                )
                header_prefix = None
        else:
            header_prefix = None

        if license_line:
            license_match = LICENSE_REGEX.match(license_line.strip())
            if license_match:
                license_prefix = license_match.group("prefix")
                license_ok = header_prefix is None or license_prefix == header_prefix
            else:
                violations.append(
                    Violation(
                        rel_path,
                        "SPDX license identifier line format is invalid.",
                        "SPDX-License-Identifier 行格式不正确。",
                    )
                )
        else:
            license_prefix = None

        if header_prefix and license_line and not license_ok:
            violations.append(
                Violation(
                    rel_path,
                    "SPDX header and license lines must use the same comment prefix.",
                    "SPDX 版权头与许可证行需使用相同的注释前缀。",
                )
            )

        status = status.upper()
        if status == "A":
            validate_new_file(rel_path, years_field, license_ok, violations)
        elif status == "M":
            creation_year = get_creation_year(rel_path)
            validate_modified_file(rel_path, years_field, license_ok, creation_year, violations)
        elif status == "C":
            # Treat copies as modifications.
            creation_year = get_creation_year(rel_path)
            validate_modified_file(rel_path, years_field, license_ok, creation_year, violations)

    if violations:
        print("SPDX header validation failed:\n")
        for problem in violations:
            print(problem)
            print()
        return 1

    print("All checked files have valid SPDX headers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
