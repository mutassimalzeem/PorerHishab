"""it contains rule-based categorization helpers.

Backwards-compatible shim. The canonical implementation now lives in
``backend/app/services/categorization/categorizer.py`` so that it can be
imported from any working directory. This module is kept so that existing
``from categorizer import categorize_text`` usage (repository root) keeps
working.
"""

import sys
from pathlib import Path

# Make the `app` package importable regardless of the current directory.
_BACKEND_DIR = Path(__file__).resolve().parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.services.categorization.categorizer import (  # noqa: E402
    COMPILED,
    RULES,
    categorize_text,
)

__all__ = ["COMPILED", "RULES", "categorize_text"]
