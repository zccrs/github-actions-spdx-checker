<!-- SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd. -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# SPDX Header Checker

A GitHub Action to validate SPDX copyright headers on pull requests. Ensures all new and modified files have correct SPDX headers with proper year formatting.

## Features

✅ **New Files**: Validates that new files include SPDX headers with the current year
✅ **Modified Files**: Ensures modified files update to current year or use proper year ranges
✅ **File Creation Detection**: Automatically detects original file creation year from git history
✅ **Flexible Patterns**: Support for including/excluding files by glob patterns
✅ **Bilingual Messages**: Error messages in both English and Simplified Chinese
✅ **Multi-Format Support**: Works with `//` and `#` style comments

## What It Checks

- New files must include an SPDX header with the current year
- Modified files must update their SPDX header year:
  - Same year as creation: Use single year format (e.g., `2026`)
  - Different year from creation: Use year range format (e.g., `2023-2026`)
- SPDX license identifier lines must be present
- Header and license lines must use matching comment prefixes

## Usage

### As a GitHub Action (Recommended)

Add to your `.github/workflows/spdx-check.yml`:

```yaml
name: SPDX Header Check

on:
  pull_request:
    branches: [main]

jobs:
  spdx-check:
    runs-on: ubuntu-latest
    steps:
      - uses: zccrs/github-actions-spdx-checker@v1
        with:
          base: origin/main
          include: '*.py,*.cpp,*.h'
          exclude: 'vendor/**'
```

### Inputs

- **base** (optional): Base reference to diff against (default: `origin/main`)
- **include** (optional): Comma-separated glob patterns to include (default: all files)
- **exclude** (optional): Comma-separated glob patterns to exclude (default: none)
- **year** (optional): Current year for validation (default: current UTC year)

### Local Usage

```bash
python3 scripts/check_spdx_headers.py --base origin/main
python3 scripts/check_spdx_headers.py --base origin/main --year 2024
```

## SPDX Header Format

### For C/C++/Java files:
```cpp
// SPDX-FileCopyrightText: 2026 Your Company Name
// SPDX-License-Identifier: GPL-3.0-or-later
```

### For Python/Shell/CMake files:
```python
# SPDX-FileCopyrightText: 2026 Your Company Name
# SPDX-License-Identifier: GPL-3.0-or-later
```

### For modified files (created in earlier year):
```cpp
// SPDX-FileCopyrightText: 2023-2026 Your Company Name
// SPDX-License-Identifier: GPL-3.0-or-later
```

## Error Messages

When validation fails, you'll see clear error messages:

```
[file.py] New files must use a single year (no range) in the SPDX header.
新增文件的 SPDX 版权头必须只包含当前年份，不能使用年份范围。

[oldfile.py] File predates current year; update SPDX header to use a year range 2023-2026.
文件创建年份早于当前年份，请将 SPDX 版权头更新为年份范围 2023-2026。
```

## Testing

Run the test suite locally:

```bash
pytest tests/ -v --cov=scripts
```

## Supported Python Versions

- Python 3.9+
- Python 3.10+
- Python 3.11+
- Python 3.12+

## License

GPL-3.0-or-later
