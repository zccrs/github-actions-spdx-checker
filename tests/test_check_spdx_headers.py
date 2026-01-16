# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests for SPDX header validation script."""

import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

from scripts.check_spdx_headers import (
    SPDX_HEADER_REGEX,
    COPYRIGHT_HEADER_REGEX,
    LICENSE_REGEX,
    Violation,
    extract_header_lines,
    parse_years,
    validate_new_file,
    validate_modified_file,
)


class TestHeaderRegex(unittest.TestCase):
    """Test SPDX and Copyright header regex matching."""

    def test_valid_spdx_header_single_year(self):
        """Test matching valid SPDX header with single year."""
        line = "// SPDX-FileCopyrightText: 2026 Alice Corp"
        match = SPDX_HEADER_REGEX.match(line)
        self.assertIsNotNone(match)
        self.assertEqual(match.group("prefix"), "//")
        self.assertEqual(match.group("years"), "2026")
        self.assertEqual(match.group("holder"), "Alice Corp")

    def test_valid_spdx_header_year_range(self):
        """Test matching valid SPDX header with year range."""
        line = "# SPDX-FileCopyrightText: 2023-2026 Bob Inc."
        match = SPDX_HEADER_REGEX.match(line)
        self.assertIsNotNone(match)
        self.assertEqual(match.group("prefix"), "#")
        self.assertEqual(match.group("years"), "2023-2026")
        self.assertEqual(match.group("holder"), "Bob Inc.")

    def test_valid_spdx_header_with_extra_spaces(self):
        """Test matching SPDX header with extra spaces."""
        line = "//  SPDX-FileCopyrightText:  2026  Charlie Ltd"
        match = SPDX_HEADER_REGEX.match(line)
        self.assertIsNotNone(match)
        self.assertEqual(match.group("years"), "2026")

    def test_valid_copyright_header_single_year(self):
        """Test matching valid Copyright (C) header with single year."""
        line = "// Copyright (C) 2026 UnionTech Software Technology Co., Ltd."
        match = COPYRIGHT_HEADER_REGEX.match(line)
        self.assertIsNotNone(match)
        self.assertEqual(match.group("prefix"), "//")
        self.assertEqual(match.group("years"), "2026")
        self.assertEqual(match.group("holder"), "UnionTech Software Technology Co., Ltd.")

    def test_valid_copyright_header_year_range(self):
        """Test matching valid Copyright (C) header with year range."""
        line = "# Copyright (C) 2020-2026 Some Company"
        match = COPYRIGHT_HEADER_REGEX.match(line)
        self.assertIsNotNone(match)
        self.assertEqual(match.group("prefix"), "#")
        self.assertEqual(match.group("years"), "2020-2026")
        self.assertEqual(match.group("holder"), "Some Company")

    def test_invalid_header_wrong_format(self):
        """Test that malformed headers don't match."""
        line = "// Copyright: 2026 Alice Corp"
        match = SPDX_HEADER_REGEX.match(line)
        self.assertIsNone(match)
        match = COPYRIGHT_HEADER_REGEX.match(line)
        self.assertIsNone(match)

    def test_invalid_header_missing_holder(self):
        """Test header with missing holder."""
        line = "// SPDX-FileCopyrightText: 2026"
        match = SPDX_HEADER_REGEX.match(line)
        self.assertIsNone(match)


class TestLicenseRegex(unittest.TestCase):
    """Test SPDX license identifier regex matching."""

    def test_valid_license_cpp(self):
        """Test matching valid C++ license line."""
        line = "// SPDX-License-Identifier: GPL-3.0-or-later"
        match = LICENSE_REGEX.match(line)
        self.assertIsNotNone(match)
        self.assertEqual(match.group("prefix"), "//")
        self.assertEqual(match.group("license"), "GPL-3.0-or-later")

    def test_valid_license_python(self):
        """Test matching valid Python license line."""
        line = "# SPDX-License-Identifier: MIT"
        match = LICENSE_REGEX.match(line)
        self.assertIsNotNone(match)
        self.assertEqual(match.group("prefix"), "#")
        self.assertEqual(match.group("license"), "MIT")

    def test_invalid_license_wrong_format(self):
        """Test that malformed license lines don't match."""
        line = "// License-Identifier: GPL-3.0-or-later"
        match = LICENSE_REGEX.match(line)
        self.assertIsNone(match)


class TestParseYears(unittest.TestCase):
    """Test year parsing."""

    def test_parse_single_year(self):
        """Test parsing single year."""
        start, end = parse_years("2026")
        self.assertEqual(start, 2026)
        self.assertIsNone(end)

    def test_parse_year_range(self):
        """Test parsing year range."""
        start, end = parse_years("2023-2026")
        self.assertEqual(start, 2023)
        self.assertEqual(end, 2026)


class TestExtractHeaderLines(unittest.TestCase):
    """Test SPDX header line extraction."""

    def test_extract_valid_headers(self):
        """Test extracting valid header and license lines."""
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("# SPDX-FileCopyrightText: 2026 Test Corp\n")
            f.write("# SPDX-License-Identifier: GPL-3.0-or-later\n")
            f.write("\n")
            f.write("print('hello')\n")
            f.flush()

            header, license_line = extract_header_lines(Path(f.name))
            self.assertIsNotNone(header)
            self.assertIn("2026", header)
            self.assertIsNotNone(license_line)
            self.assertIn("GPL-3.0-or-later", license_line)

    def test_extract_missing_license(self):
        """Test extracting when license line is missing."""
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("# SPDX-FileCopyrightText: 2026 Test Corp\n")
            f.write("\n")
            f.write("print('hello')\n")
            f.flush()

            header, license_line = extract_header_lines(Path(f.name))
            self.assertIsNotNone(header)
            self.assertIsNone(license_line)

    def test_extract_empty_file(self):
        """Test extracting from empty file."""
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.flush()

            header, license_line = extract_header_lines(Path(f.name))
            self.assertIsNone(header)
            self.assertIsNone(license_line)


class TestValidateNewFile(unittest.TestCase):
    """Test new file validation logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.current_year = 2026

    def test_new_file_missing_header(self):
        """Test that missing header (None years_field) is handled gracefully."""
        violations = []
        validate_new_file("test.py", None, False, self.current_year, None, None, violations)
        # When years_field is None, the function returns early without adding violations
        # The missing header should be caught earlier in the main loop
        self.assertEqual(len(violations), 0)

    def test_new_file_invalid_year(self):
        """Test that incorrect year generates violation."""
        violations = []
        header = "// SPDX-FileCopyrightText: 2025 Test Corp"
        validate_new_file("test.py", "2025", True, self.current_year, header, "Test Corp", violations)
        self.assertEqual(len(violations), 1)
        self.assertIn("should be", violations[0].message_en)
        self.assertIn("Current:", violations[0].message_en)
        self.assertIn("Expected:", violations[0].message_en)

    def test_new_file_with_year_range(self):
        """Test that year range on new file generates violation."""
        violations = []
        header = "// SPDX-FileCopyrightText: 2023-2026 Test Corp"
        validate_new_file("test.py", "2023-2026", True, self.current_year, header, "Test Corp", violations)
        self.assertEqual(len(violations), 1)
        self.assertIn("single year", violations[0].message_en)
        self.assertIn("Current:", violations[0].message_en)
        self.assertIn("Expected:", violations[0].message_en)

    def test_new_file_valid(self):
        """Test valid new file generates no violations."""
        violations = []
        header = f"// SPDX-FileCopyrightText: {self.current_year} Test Corp"
        validate_new_file("test.py", str(self.current_year), True, self.current_year, header, "Test Corp", violations)
        self.assertEqual(len(violations), 0)


class TestValidateModifiedFile(unittest.TestCase):
    """Test modified file validation logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.current_year = 2026

    def test_modified_file_missing_header(self):
        """Test that missing header (None years_field) is handled gracefully."""
        violations = []
        validate_modified_file("test.py", None, False, 2023, self.current_year, None, None, violations)
        # When years_field is None, the function returns early without adding violations
        # The missing header should be caught earlier in the main loop
        self.assertEqual(len(violations), 0)

    def test_modified_file_same_year_current(self):
        """Test modified file created in current year."""
        violations = []
        header = f"// SPDX-FileCopyrightText: {self.current_year} Test Corp"
        validate_modified_file("test.py", str(self.current_year), True, self.current_year, self.current_year, header, "Test Corp", violations)
        self.assertEqual(len(violations), 0)

    def test_modified_file_older_without_range(self):
        """Test modified file from older year without range format."""
        violations = []
        header = "// SPDX-FileCopyrightText: 2023 Test Corp"
        validate_modified_file("test.py", "2023", True, 2023, self.current_year, header, "Test Corp", violations)
        self.assertEqual(len(violations), 1)
        self.assertIn("year range", violations[0].message_en)
        self.assertIn("Current:", violations[0].message_en)
        self.assertIn("Expected:", violations[0].message_en)

    def test_modified_file_with_correct_range(self):
        """Test modified file with correct year range."""
        violations = []
        header = f"// SPDX-FileCopyrightText: 2023-{self.current_year} Test Corp"
        validate_modified_file("test.py", f"2023-{self.current_year}", True, 2023, self.current_year, header, "Test Corp", violations)
        self.assertEqual(len(violations), 0)

    def test_modified_file_with_incorrect_range_end(self):
        """Test modified file with incorrect range end year."""
        violations = []
        header = "// SPDX-FileCopyrightText: 2023-2025 Test Corp"
        validate_modified_file("test.py", "2023-2025", True, 2023, self.current_year, header, "Test Corp", violations)
        self.assertEqual(len(violations), 1)
        self.assertIn("Update SPDX year range", violations[0].message_en)
        self.assertIn("Current:", violations[0].message_en)
        self.assertIn("Expected:", violations[0].message_en)

    def test_modified_file_identical_range(self):
        """Test modified file with identical start and end year."""
        violations = []
        header = f"// SPDX-FileCopyrightText: {self.current_year}-{self.current_year} Test Corp"
        validate_modified_file("test.py", f"{self.current_year}-{self.current_year}", True, self.current_year, self.current_year, header, "Test Corp", violations)
        self.assertEqual(len(violations), 1)
        self.assertIn("identical start and end", violations[0].message_en)
        self.assertIn("Current:", violations[0].message_en)
        self.assertIn("Expected:", violations[0].message_en)


class TestViolationClass(unittest.TestCase):
    """Test Violation class."""

    def test_violation_string_representation(self):
        """Test violation string output."""
        v = Violation("test.py", "Error in English", "错误的中文")
        output = str(v)
        self.assertIn("test.py", output)
        self.assertIn("Error in English", output)
        self.assertIn("错误的中文", output)


class TestHolderFiltering(unittest.TestCase):
    """Test holder pattern filtering functionality."""

    def test_holder_pattern_matching(self):
        """Test holder pattern matching with various patterns."""
        import fnmatch

        # Test exact match
        self.assertTrue(fnmatch.fnmatch("UnionTech Software", "UnionTech Software"))

        # Test wildcard patterns
        self.assertTrue(fnmatch.fnmatch("UnionTech Software Technology Co., Ltd.", "*UnionTech*"))
        self.assertTrue(fnmatch.fnmatch("Alice Corp", "*Corp"))
        self.assertTrue(fnmatch.fnmatch("Bob Inc.", "Bob*"))

        # Test non-matching patterns
        self.assertFalse(fnmatch.fnmatch("Alice Corp", "*UnionTech*"))
        self.assertFalse(fnmatch.fnmatch("UnionTech Software", "*Microsoft*"))

    def test_main_with_holder_filtering(self):
        """Test main function with holder pattern filtering."""
        from scripts.check_spdx_headers import main
        from unittest.mock import patch
        import tempfile
        import os

        # Create temporary files with different holders
        with tempfile.TemporaryDirectory() as tmp_dir:
            # File with UnionTech holder
            file1 = os.path.join(tmp_dir, "file1.py")
            with open(file1, "w") as f:
                f.write("# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.\n")
                f.write("# SPDX-License-Identifier: GPL-3.0-or-later\n")
                f.write("print('hello')\n")

            # File with different holder
            file2 = os.path.join(tmp_dir, "file2.py")
            with open(file2, "w") as f:
                f.write("# SPDX-FileCopyrightText: 2026 Microsoft Corporation\n")
                f.write("# SPDX-License-Identifier: MIT\n")
                f.write("print('world')\n")

            # Mock git operations and change to temp directory
            with patch('scripts.check_spdx_headers.run_git') as mock_git:
                # Set up return values for git commands
                def git_side_effect(*args):
                    if args[0][0] == "rev-parse":
                        return ""  # git rev-parse
                    elif args[0][0] == "diff":
                        return f"A\t{os.path.basename(file1)}\nA\t{os.path.basename(file2)}\n"  # git diff --name-status
                    else:
                        return ""

                mock_git.side_effect = git_side_effect
        import tempfile
        import os
        from io import StringIO
        import sys

        with tempfile.TemporaryDirectory() as tmp_dir:
            # File with different holder
            file1 = os.path.join(tmp_dir, "file1.py")
            with open(file1, "w") as f:
                f.write("# SPDX-FileCopyrightText: 2026 Alice Corporation\n")
                f.write("# SPDX-License-Identifier: GPL-3.0-or-later\n")
                f.write("print('test')\n")

            with patch('scripts.check_spdx_headers.run_git') as mock_git:
                # Set up return values for git commands
                def git_side_effect(*args):
                    if args[0][0] == "rev-parse":
                        return ""  # git rev-parse
                    elif args[0][0] == "diff":
                        return f"A\t{os.path.basename(file1)}\n"  # git diff --name-status
                    else:
                        return ""

                mock_git.side_effect = git_side_effect

                old_cwd = os.getcwd()
                os.chdir(tmp_dir)

                try:
                    # Capture stdout to check debug output
                    captured_output = StringIO()
                    with patch('sys.stdout', captured_output):
                        result = main(['--base', 'HEAD', '--holder', '*UnionTech*', '--debug'])
                        output = captured_output.getvalue()

                    self.assertEqual(result, 0)  # Should pass as no files match holder pattern
                    self.assertIn("Ignored (holder mismatch)", output)
                    self.assertIn("File holder: 'Alice Corporation'", output)
                    self.assertIn("Pattern: '*UnionTech*'", output)
                    self.assertIn("Reason: File copyright holder does not match", output)

                finally:
                    os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
