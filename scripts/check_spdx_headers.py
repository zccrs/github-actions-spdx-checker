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
# SPDX format: // SPDX-FileCopyrightText: 2026 Company Name
SPDX_HEADER_REGEX = re.compile(
    r"^(?P<prefix>//|#)\s*SPDX-FileCopyrightText:\s*"
    r"(?P<years>\d{4}(?:\s*-\s*\d{4})?)\s+"
    r"(?P<holder>.+)$"
)
# Traditional Copyright format: // Copyright (C) 2025 Company Name
COPYRIGHT_HEADER_REGEX = re.compile(
    r"^(?P<prefix>//|#)\s*Copyright\s*\(C\)\s*"
    r"(?P<years>\d{4}(?:\s*-\s*\d{4})?)\s+"
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


def list_changed_files(base: str, head: str) -> List[Tuple[str, str]]:
    """Return a list of (status, path) for files changed since base."""

    diff_output = run_git(["diff", "--name-status", f"{base}...{head}", "--diff-filter=ACMR"])
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
        # Check for both SPDX and traditional Copyright formats
        if header_line is None and (SPDX_HEADER_REGEX.match(line) or COPYRIGHT_HEADER_REGEX.match(line)):
            header_line = line
            continue
        if header_line and license_line is None and LICENSE_REGEX.match(line):
            license_line = line
            break
    return header_line, license_line


def extract_header_lines_from_git(
    ref: str, path: str
) -> Tuple[Optional[str], Optional[str]]:
    """Return the SPDX header and license lines from a specific git commit."""

    try:
        output = run_git(["show", f"{ref}:{path}"])
    except RuntimeError:
        return None, None

    header_line = None
    license_line = None
    for raw_line in output.splitlines()[:10]:
        line = raw_line.strip("\ufeff\n\r")
        if not line.strip():
            continue
        # Check for both SPDX and traditional Copyright formats
        if header_line is None and (
            SPDX_HEADER_REGEX.match(line) or COPYRIGHT_HEADER_REGEX.match(line)
        ):
            header_line = line
            continue
        if header_line and license_line is None and LICENSE_REGEX.match(line):
            license_line = line
            break
    return header_line, license_line


def parse_years(year_field: str) -> Tuple[int, Optional[int]]:
    """Split a SPDX year field into start and end years."""

    if "-" in year_field:
        start, end = year_field.split("-", 1)
        return int(start.strip()), int(end.strip())
    return int(year_field.strip()), None


def validate_new_file(
    path: str,
    years_field: Optional[str],
    license_ok: bool,
    current_year: int,
    header_line: Optional[str],
    holder: Optional[str],
    violations: List[Violation],
    is_copyright_format: bool = False,
    header_prefix: str = "//",
) -> None:
    # If years_field is None, it means the header format was already reported as invalid
    # or the file was skipped, so we don't need to report again
    if years_field is None:
        return

    start_year, end_year = parse_years(years_field)
    if end_year is not None:
        if is_copyright_format:
            correct_header = f"Copyright (C) {current_year} {holder or 'Your Company Name'}"
        else:
            correct_header = f"SPDX-FileCopyrightText: {current_year} {holder or 'Your Company Name'}"
        violations.append(
            Violation(
                path,
                (
                    f"New files must use a single year (no range) in the SPDX header.\n"
                    f"  Reason: This is a newly added file (current year: {current_year})\n"
                    f"  Current: {header_line.strip() if header_line else 'N/A'}\n"
                    f"  Expected: {header_prefix} {correct_header}"
                ),
                (
                    f"新增文件的 SPDX 版权头必须只包含当前年份，不能使用年份范围。\n"
                    f"  原因：这是新增的文件（当前年份：{current_year}）\n"
                    f"  当前内容：{header_line.strip() if header_line else 'N/A'}\n"
                    f"  建议修改：{header_prefix} {correct_header}"
                ),
            )
        )
    elif start_year != current_year:
        if is_copyright_format:
            correct_header = f"Copyright (C) {current_year} {holder or 'Your Company Name'}"
        else:
            correct_header = f"SPDX-FileCopyrightText: {current_year} {holder or 'Your Company Name'}"
        violations.append(
            Violation(
                path,
                (
                    f"SPDX header year should be {current_year} for new files.\n"
                    f"  Reason: This is a newly added file created in {current_year}\n"
                    f"  Current: {header_line.strip() if header_line else 'N/A'}\n"
                    f"  Expected: {header_prefix} {correct_header}"
                ),
                (
                    f"新增文件的 SPDX 版权年份应为 {current_year}。\n"
                    f"  原因：这是在 {current_year} 年新增的文件\n"
                    f"  当前内容：{header_line.strip() if header_line else 'N/A'}\n"
                    f"  建议修改：{header_prefix} {correct_header}"
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
    is_copyright_format: bool = False,
    header_prefix: str = "//",
) -> None:
    # If years_field is None, it means the header format was already reported as invalid
    # or the file was skipped, so we don't need to report again
    if years_field is None:
        return

    start_year, end_year = parse_years(years_field)
    if end_year is None:
        if start_year != current_year:
            if is_copyright_format:
                correct_header = (
                    f"Copyright (C) {current_year} {holder or 'Your Company Name'}"
                )
            else:
                correct_header = f"SPDX-FileCopyrightText: {current_year} {holder or 'Your Company Name'}"
            violations.append(
                Violation(
                    path,
                    (
                        f"SPDX header year should be {current_year}.\n"
                        f"  Reason: File was modified in {current_year}\n"
                        f"  Current: {header_line.strip() if header_line else 'N/A'}\n"
                        f"  Expected: {header_prefix} {correct_header}"
                    ),
                    (
                        f"请将 SPDX 版权年份更新为 {current_year}。\n"
                        f"  原因：文件在 {current_year} 年被修改\n"
                        f"  当前内容：{header_line.strip() if header_line else 'N/A'}\n"
                        f"  建议修改：{header_prefix} {correct_header}"
                    ),
                )
            )
    else:
        if start_year > end_year:
            if is_copyright_format:
                correct_header = f"Copyright (C) {end_year}-{start_year} {holder or 'Your Company Name'}"
            else:
                correct_header = f"SPDX-FileCopyrightText: {end_year}-{start_year} {holder or 'Your Company Name'}"
            violations.append(
                Violation(
                    path,
                    (
                        f"Invalid SPDX year range (start year greater than end year).\n"
                        f"  Current: {header_line.strip() if header_line else 'N/A'}\n"
                        f"  Expected: {header_prefix} {correct_header}"
                    ),
                    (
                        f"SPDX 年份范围不合法：起始年份大于结束年份。\n"
                        f"  当前内容：{header_line.strip() if header_line else 'N/A'}\n"
                        f"  建议修改：{header_prefix} {correct_header}"
                    ),
                )
            )
        if end_year != current_year:
            if is_copyright_format:
                correct_header = f"Copyright (C) {start_year}-{current_year} {holder or 'Your Company Name'}"
            else:
                correct_header = f"SPDX-FileCopyrightText: {start_year}-{current_year} {holder or 'Your Company Name'}"
            violations.append(
                Violation(
                    path,
                    (
                        f"Update SPDX year range end to {current_year}.\n"
                        f"  Reason: File was modified in {current_year}, range end should reflect this\n"
                        f"  Current: {header_line.strip() if header_line else 'N/A'}\n"
                        f"  Expected: {header_prefix} {correct_header}"
                    ),
                    (
                        f"请将 SPDX 年份范围的结束年份更新为 {current_year}。\n"
                        f"  原因：文件在 {current_year} 年被修改，年份范围应反映最新修改时间\n"
                        f"  当前内容：{header_line.strip() if header_line else 'N/A'}\n"
                        f"  建议修改：{header_prefix} {correct_header}"
                    ),
                )
            )
        if start_year == end_year:
            if is_copyright_format:
                correct_header = f"Copyright (C) {start_year} {holder or 'Your Company Name'}"
            else:
                correct_header = f"SPDX-FileCopyrightText: {start_year} {holder or 'Your Company Name'}"
            violations.append(
                Violation(
                    path,
                    (
                        f"Year range uses identical start and end; use single year format instead.\n"
                        f"  Reason: When start and end years are the same, use single year format\n"
                        f"  Current: {header_line.strip() if header_line else 'N/A'}\n"
                        f"  Expected: {header_prefix} {correct_header}"
                    ),
                    (
                        f"年份范围的起止相同，应改为单年份格式。\n"
                        f"  原因：起止年份相同时应使用单年份格式\n"
                        f"  当前内容：{header_line.strip() if header_line else 'N/A'}\n"
                        f"  建议修改：{header_prefix} {correct_header}"
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
    parser.add_argument(
        "--holder",
        type=str,
        default="",
        help="Only check files with matching copyright holder (supports wildcards like '*UnionTech*'). Empty means check all files.",
    )
    parser.add_argument(
        "--head",
        default=os.environ.get("GITHUB_HEAD_REF", "HEAD"),
        help="Head reference to diff against (default: environment GITHUB_HEAD_REF or HEAD)",
    )
    args = parser.parse_args(argv)
    current_year = args.year
    debug = args.debug
    check_all_files = args.all_files
    holder_pattern = args.holder

    base_ref = args.base or parser.get_default('base')
    head_ref = args.head or parser.get_default('head')

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
            print(f"[DEBUG] Running in diff mode: checking files changed since {base_ref}...{head_ref}")
        changed = list_changed_files(base_ref, head_ref)

    if not changed:
        print(f"No applicable file changes detected since {base_ref}...{head_ref}; skipping SPDX validation.")
        return 0

    if debug:
        print(f"[DEBUG] Found {len(changed)} file(s) to process")

    include_patterns = [pattern for pattern in args.include or []]
    exclude_patterns = [pattern for pattern in args.exclude or []]

    violations: List[Violation] = []
    checked_count = 0
    skipped_count = 0
    ignored_count = 0
    holder_ignored_count = 0
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

        # Ignore files without SPDX headers - they are not in scope for validation
        if not header_line:
            if debug:
                print(f"[DEBUG] ○ Ignored (no SPDX header): {rel_path}")
            ignored_count += 1
            continue

        # Extract holder first to check if we should validate this file
        years_field: Optional[str] = None
        holder: Optional[str] = None
        header_match = None
        is_copyright_format = False
        if header_line:
            # Try SPDX format first, then traditional Copyright format
            header_match = SPDX_HEADER_REGEX.match(header_line.strip())
            if not header_match:
                header_match = COPYRIGHT_HEADER_REGEX.match(header_line.strip())
                if header_match:
                    is_copyright_format = True
        if header_match:
            holder = header_match.group("holder")

        # If holder pattern is specified, check if this file's holder matches
        if holder_pattern and holder:
            if not fnmatch.fnmatch(holder, holder_pattern):
                if debug:
                    print(f"[DEBUG] ○ Ignored (holder mismatch): {rel_path}")
                    print(f"    File holder: '{holder}'")
                    print(f"    Pattern: '{holder_pattern}'")
                    print(f"    Reason: File copyright holder does not match the specified holder pattern")
                holder_ignored_count += 1
                continue

        checked_count += 1
        license_ok = False
        file_violations_before = len(violations)

        if header_line:
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
            validate_new_file(rel_path, years_field, license_ok, current_year, header_line, holder, violations, is_copyright_format, header_prefix or "//")
        elif status == "M":
            validate_modified_file(rel_path, years_field, license_ok, None, current_year, header_line, holder, violations, is_copyright_format, header_prefix or "//")
            # Check if base version had a different single year that should be preserved
            if years_field and header_line:
                base_header_line, _ = extract_header_lines_from_git(base_ref, rel_path)
                if base_header_line:
                    base_match = SPDX_HEADER_REGEX.match(base_header_line.strip())
                    if not base_match:
                        base_match = COPYRIGHT_HEADER_REGEX.match(
                            base_header_line.strip()
                        )
                    if base_match:
                        base_years_field = base_match.group("years")
                        base_start_year, base_end_year = parse_years(base_years_field)
                        current_start_year, current_end_year = parse_years(years_field)
                        # Extract the earliest year from base version
                        base_min_year = base_start_year
                        # Check if current version includes base version's start year
                        start_year_lost = False
                        if current_end_year is None:
                            # Current version uses single year
                            if current_start_year != base_min_year:
                                start_year_lost = True
                        else:
                            # Current version uses range
                            if current_start_year != base_min_year:
                                start_year_lost = True
                        # If base version's start year is lost in current version
                        if start_year_lost:
                            range_start_year = base_min_year
                            # Use the larger of current version's end and current calendar year
                            if current_end_year is None:
                                range_end_year = max(current_start_year, current_year)
                            else:
                                range_end_year = max(current_end_year, current_year)
                            if range_start_year == range_end_year:
                                if is_copyright_format:
                                    correct_header = f"Copyright (C) {range_start_year} {holder or 'Your Company Name'}"
                                else:
                                    correct_header = f"SPDX-FileCopyrightText: {range_start_year} {holder or 'Your Company Name'}"
                            else:
                                if is_copyright_format:
                                    correct_header = f"Copyright (C) {range_start_year}-{range_end_year} {holder or 'Your Company Name'}"
                                else:
                                    correct_header = f"SPDX-FileCopyrightText: {range_start_year}-{range_end_year} {holder or 'Your Company Name'}"
                            violations.append(
                                Violation(
                                    rel_path,
                                    (
                                        f"Copyright start year from base version ({base_min_year}) is missing in current version.\n"
                                        f"  Reason: Base version had start year {base_min_year}, which should be preserved\n"
                                        f"  Current: {header_line.strip() if header_line else 'N/A'}\n"
                                        f"  Expected: {header_prefix or '//'} {correct_header}"
                                    ),
                                    (
                                        f"基础版本的版权起始年份 ({base_min_year}) 在当前版本中丢失。\n"
                                        f"  原因：基础版本有起始年份 {base_min_year}，应该予以保留\n"
                                        f"  当前内容：{header_line.strip() if header_line else 'N/A'}\n"
                                        f"  建议修改：{header_prefix or '//'} {correct_header}"
                                    ),
                                )
                            )
        elif status == "C":
            # Treat copies as modifications.
            validate_modified_file(rel_path, years_field, license_ok, None, current_year, header_line, holder, violations, is_copyright_format, header_prefix or "//")

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
        print(f"[DEBUG] Summary: {checked_count} checked, {passed_count} passed, {len(violations)} failed, {skipped_count} skipped, {ignored_count} ignored (no header), {holder_ignored_count} ignored (holder mismatch)")

    # Print summary for all modes
    print("\n" + "=" * 60)
    print("SPDX Header Validation Summary / SPDX 头验证汇总")
    print("=" * 60)
    print(f"Checked / 已检查:  {checked_count}")
    print(f"Passed / 通过:     {passed_count}")
    print(f"Failed / 失败:     {len(violations)}")
    print(f"Skipped / 跳过:    {skipped_count}  (excluded by patterns)")
    print(f"Ignored / 忽略:    {ignored_count}  (no SPDX header found)")
    if holder_ignored_count > 0:
        print(f"Ignored / 忽略:    {holder_ignored_count}  (holder pattern mismatch)")
    print("=" * 60)

    if violations:
        print("\nSPDX header validation failed:\n")
        for problem in violations:
            print(problem)
            print()
        return 1

    print("\n✓ All checked files have valid SPDX headers.")
    print("✓ 所有检查的文件都有有效的 SPDX 头。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
