# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-3.0-or-later

"""Pytest configuration."""

import sys
from pathlib import Path

# Add scripts directory to path so tests can import the module
sys.path.insert(0, str(Path(__file__).parent))
