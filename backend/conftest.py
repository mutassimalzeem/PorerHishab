"""Pytest bootstrap for the backend package.

Ensures the repository-root ``.env`` is discoverable and that ``backend/`` is
on ``sys.path``, so tests run identically from the repository root or from
``backend/``.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent

for path in (str(BACKEND_DIR), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)
