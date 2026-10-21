"""Pytest bootstrap.

Puts ``backend/`` on ``sys.path`` so the ``app`` package imports cleanly and
makes the repository-root ``.env`` discoverable, regardless of the directory
pytest is invoked from.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = REPO_ROOT / "backend"

for path in (str(BACKEND_DIR), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)
