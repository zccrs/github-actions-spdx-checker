<!-- SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd. -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# GitHub Actions SPDX Header Checker

This repository provides a reusable GitHub Actions workflow that validates SPDX copyright headers on pull requests. It relies on the Python helper script located at `scripts/check_spdx_headers.py`.

## What It Checks

- New files include an SPDX header that uses the current calendar year.
- Modified files update their SPDX header to the current year.
- Older files retain their original creation year as the left side of a year range (e.g. `2023-2026`).
- SPDX license identifier lines are present and aligned with the header comment style.

## Usage

The workflow defined in `.github/workflows/spdx-check.yml` runs automatically for pull requests once copied into your repository. It can also be invoked manually via the **Run workflow** button in GitHub.

To run the validation locally:

```bash
python3 scripts/check_spdx_headers.py --base origin/main
```

Ensure your local clone has the relevant base branch fetched with full history (`git fetch origin main --depth=0`).
