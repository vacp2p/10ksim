"""Every module under src/ must import.

The linters parse files without executing them, so they catch a syntax error but not a
broken import, and pytest only imports what a test reaches. A module nothing imports is
never executed at all, which is how a rename in one file left another importing a name
that no longer existed and still went green.
"""

import importlib
from pathlib import Path
from typing import List

import pytest

SRC = Path(__file__).resolve().parents[1]


def _module_names() -> List[str]:
    root = SRC.parent
    names = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        parts = list(path.relative_to(root).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            names.append(".".join(parts))
    return names


@pytest.mark.parametrize("module", _module_names())
def test_module_imports(module: str) -> None:
    importlib.import_module(module)
