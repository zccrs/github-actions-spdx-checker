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

COMMENT_PREFIXES = ("//", "#")
HEADER_REGEX = re.compile(
    r"^(?P<prefix>//|#)\s*SPDX-FileCopyrightText:\s*"
    r"(?P<years>\d{4}(?:-\d{4})?)\s+"
    r"(?P<holder>.+)$"
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


def list_all_files() -> List[Tuple[str, str]]:
    """Return a list of (status='M', path) for all tracked files in the repository."""

    ls_output = run_git(["ls-files"])
    entries: List[Tuple[str, str]] = []
    for line in ls_output.splitlines():
        if line.strip():
            # Mark all files as 'M' (modified) for validation purposes
            entries.append(("M", line.strip()))
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
    current_year: int,
    header_line: Optional[str],
    holder: Optional[str],
    violations: List[Violation],
) -> None:
    # If years_field is None, it means the header format was already reported as invalid
    # or the file was skipped, so we don't need to report again
    if years_field is None:
        return

    start_year, end_year = parse_years(years_field)
    if end_year is not None:
        correct_header = f"SPDX-FileCopyrightText: {current_year} {holder or 'Your Company Name'}"
        violations.append(
            Violation(
                path,
                (
                    f"New files must use a single year (no range) in the SPDX header.\n"
                    f"  Current: {header_line.strip() if header_line else 'N/A'}\n"
                    f"  Expected: // {correct_header} (or # for Python/Shell)"
                ),
                (
                    f"新增文件的 SPDX 版权头必须只包含当前年份，不能使用年份范围。\n"
                    f"  当前内容：{header_line.strip() if header_line else 'N/A'}\n"
                    f"  建议修改：// {correct_header}（Python/Shell 文件用 #）"
                ),
            )
        )
    elif start_year != current_year:
        correct_header = f"SPDX-FileCopyrightText: {current_year} {holder or 'Your Company Name'}"
        violations.append(
            Violation(
                path,
                (
                    f"SPDX header year should be {current_year} for new files.\n"
                    f"  Current: {header_line.strip() if header_line else 'N/A'}\n"
                    f"  Expected: // {correct_header} (or # for Python/Shell)"
                ),
                (
                    f"新增文件的 SPDX 版权年份应为 {current_year}。\n"
                    f"  当前内容：{header_line.strip() if header_line else 'N/A'}\n"
                    f"  建议修改：// {correct_header}（Python/Shell 文件用 #）"
                ),
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
    current_year: int,
    header_line: Optional[str],
    holder: Optional[str],
    violations: List[Violation],
) -> None:
    # If years_field is None, it means the header format was already reported as invalid
    # or the file was skipped, so we don't need to report again
    if years_field is None:
        return

    start_year, end_year = parse_years(years_field)
    if end_year is None:
        if start_year != current_year:
            if creation_year and creation_year < current_year:
                range_text = f"{creation_year}-{current_year}"
                correct_header = f"SPDX-FileCopyrightText: {range_text} {holder or 'Your Company Name'}"
                violations.append(
                    Violation(
                        path,
                        (
                            f"File predates current year; update SPDX header to use a year range {range_text}.\n"
                            f"  Current: {header_line.strip() if header_line else 'N/A'}\n"
                            f"  Expected: // {correct_header} (or # for Python/Shell)"
                        ),
                        (
                            f"文件创建年份早于当前年份，请将 SPDX 版权头更新为年份范围 {range_text}。\n"
                            f"  当前内容：{header_line.strip() if header_line else 'N/A'}\n"
                            f"  建议修改：// {correct_header}（Python/Shell 文件用 #）"
                        ),
                    )
                )
            else:
                correct_header = f"SPDX-FileCopyrightText: {current_year} {holder or 'Your Company Name'}"
                violations.append(
                    Violation(
                        path,
                        (
                            f"SPDX header year should be {current_year}.\n"
                            f"  Current: {header_line.strip() if header_line else 'N/A'}\n"
                            f"  Expected: // {correct_header} (or # for Python/Shell)"
                        ),
                        (
                            f"请将 SPDX 版权年份更新为 {current_year}。\n"
                            f"  当前内容：{header_line.strip() if header_line else 'N/A'}\n"
                            f"  建议修改：// {correct_header}（Python/Shell 文件用 #）"
                        ),
                    )
                )
        elif creation_year and creation_year < current_year:
            range_text = f"{creation_year}-{current_year}"
            correct_header = f"SPDX-FileCopyrightText: {range_text} {holder or 'Your Company Name'}"
            violations.append(
                Violation(
                    path,
                    (
                        f"File has earlier creation year; use range format {range_text}.\n"
                        f"  Current: {header_line.strip() if header_line else 'N/A'}\n"
                        f"  Expected: // {correct_header} (or # for Python/Shell)"
                    ),
                    (
                        f"该文件创建于较早年份，应使用年份范围格式 {range_text}。\n"
                        f"  当前内容：{header_line.strip() if header_line else 'N/A'}\n"
                        f"  建议修改：// {correct_header}（Python/Shell 文件用 #）"
                    ),
                )
            )
    else:
        if start_year > end_year:
            correct_header = f"SPDX-FileCopyrightText: {end_year}-{start_year} {holder or 'Your Company Name'}"
            violations.append(
                Violation(
                    path,
                    (
                        f"Invalid SPDX year range (start year greater than end year).\n"
                        f"  Current: {header_line.strip() if header_line else 'N/A'}\n"
                        f"  Expected: // {correct_header} (or # for Python/Shell)"
                    ),
                    (
                        f"SPDX 年份范围不合法：起始年份大于结束年份。\n"
                        f"  当前内容：{header_line.strip() if header_line else 'N/A'}\n"
                        f"  建议修改：// {correct_header}（Python/Shell 文件用 #）"
                    ),
                )
            )
        if end_year != current_year:
            correct_header = f"SPDX-FileCopyrightText: {start_year}-{current_year} {holder or 'Your Company Name'}"
            violations.append(
                Violation(
                    path,
                    (
                        f"Update SPDX year range end to {current_year}.\n"
                        f"  Current: {header_line.strip() if header_line else 'N/A'}\n"
                        f"  Expected: // {correct_header} (or # for Python/Shell)"
                    ),
                    (
                        f"请将 SPDX 年份范围的结束年份更新为 {current_year}。\n"
                        f"  当前内容：{header_line.strip() if header_line else 'N/A'}\n"
                        f"  建议修改：// {correct_header}（Python/Shell 文件用 #）"
                    ),
                )
            )
        if creation_year and start_year != creation_year:
            correct_header = f"SPDX-FileCopyrightText: {creation_year}-{end_year} {holder or 'Your Company Name'}"
            violations.append(
                Violation(
                    path,
                    (
                        f"Year range should start at the file creation year {creation_year}.\n"
                        f"  Current: {header_line.strip() if header_line else 'N/A'}\n"
                        f"  Expected: // {correct_header} (or # for Python/Shell)"
                    ),
                    (
                        f"年份范围应以文件创建年份 {creation_year} 开始。\n"
                        f"  当前内容：{header_line.strip() if header_line else 'N/A'}\n"
                        f"  建议修改：// {correct_header}（Python/Shell 文件用 #）"
                    ),
                )
            )
        if start_year == end_year:
            correct_header = f"SPDX-FileCopyrightText: {start_year} {holder or 'Your Company Name'}"
            violations.append(
                Violation(
                    path,
                    (
                        f"Year range uses identical start and end; use single year format instead.\n"
                        f"  Current: {header_line.strip() if header_line else 'N/A'}\n"
                        f"  Expected: // {correct_header} (or # for Python/Shell)"
                    ),
                    (
                        f"年份范围的起止相同，应改为单年份格式。\n"
                        f"  当前内容：{header_line.strip() if header_line else 'N/A'}\n"
                        f"  建议修改：// {correct_header}（Python/Shell 文件用 #）"
                    ),
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
    parser.add_argument(
        "--year",
        type=int,
        default=_dt.datetime.now(_dt.timezone.utc).year,
        help="Current year for validation (default: current UTC year)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with detailed output for each file",
    )
    parser.add_argument(
        "--all-files",
        action="store_true",
        help="Check all files in repository instead of only changed files",
    )
    args = parser.parse_args(argv)
    current_year = args.year
    debug = args.debug
    check_all_files = args.all_files

    base_ref = args.base

    if check_all_files:
        if debug:
            print("[DEBUG] Running in all-files mode: checking all tracked files in repository")
        changed = list_all_files()
    else:
        try:
            run_git(["rev-parse", base_ref])
        except RuntimeError as exc:
            print(exc, file=sys.stderr)
            return 2
        if debug:
            print(f"[DEBUG] Running in diff mode: checking files changed since {base_ref}")
        changed = list_changed_files(base_ref)

    if not changed:
        print("No applicable file changes detected; skipping SPDX validation.")
        return 0

    if debug:
        print(f"[DEBUG] Found {len(changed)} file(s) to process")

    include_patterns = [pattern for pattern in args.include or []]
    exclude_patterns = [pattern for pattern in args.exclude or []]

    violations: List[Violation] = []
    checked_count = 0
    skipped_count = 0
    passed_count = 0

    for status, rel_path in changed:
        path_obj = pathlib.Path(rel_path)
        path_posix = pathlib.PurePosixPath(rel_path)
        if include_patterns and not any(fnmatch.fnmatch(path_posix.as_posix(), pattern) for pattern in include_patterns):
            if debug:
                print(f"[DEBUG] ⊘ Skipped (not in include patterns): {rel_path}")
            skipped_count += 1
            continue
        if exclude_patterns and any(fnmatch.fnmatch(path_posix.as_posix(), pattern) for pattern in exclude_patterns):
            if debug:
                print(f"[DEBUG] ⊘ Skipped (in exclude patterns): {rel_path}")
            skipped_count += 1
            continue
        if path_obj.is_dir():
            if debug:
                print(f"[DEBUG] ⊘ Skipped (directory): {rel_path}")
            skipped_count += 1
            continue

        header_line, license_line = extract_header_lines(path_obj)

        # Skip files without SPDX headers - they are not in scope for validation
        if not header_line:
            if debug:
                print(f"[DEBUG] ⊘ Skipped (no SPDX header): {rel_path}")
            skipped_count += 1
            continue

        checked_count += 1
        years_field: Optional[str] = None
        holder: Optional[str] = None
        license_ok = False
        file_violations_before = len(violations)

        if header_line:
            header_match = HEADER_REGEX.match(header_line.strip())
            if header_match:
                years_field = header_match.group("years")
                header_prefix = header_match.group("prefix")
                holder = header_match.group("holder")
                if not holder or not holder.strip():
                    violations.append(
                        Violation(
                            rel_path,
                            "SPDX header format is invalid: missing copyright holder.",
                            "SPDX 版权头格式不正确：缺少版权持有者信息。",
                        )
                    )
                    header_prefix = None
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
            validate_new_file(rel_path, years_field, license_ok, current_year, header_line, holder, violations)
        elif status == "M":
            creation_year = get_creation_year(rel_path)
            validate_modified_file(rel_path, years_field, license_ok, creation_year, current_year, header_line, holder, violations)
        elif status == "C":
            # Treat copies as modifications.
            creation_year = get_creation_year(rel_path)
            validate_modified_file(rel_path, years_field, license_ok, creation_year, current_year, header_line, holder, violations)

        # Check if this file added new violations
        file_violations_after = len(violations)
        if file_violations_after > file_violations_before:
            if debug:
                print(f"[DEBUG] ✗ Failed: {rel_path}")
        else:
            if debug:
                print(f"[DEBUG] ✓ Passed: {rel_path}")
            passed_count += 1

    if debug:
        print(f"\n[DEBUG] Summary: {checked_count} checked, {passed_count} passed, {len(violations)} failed, {skipped_count} skipped")

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
