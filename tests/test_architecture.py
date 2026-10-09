"""Structural rules that keep the no-leakage guarantee honest.

Model code must get data only through an AsOfView. If a model module could open
the store or files directly, the as-of filter could be bypassed by accident.
"""

from __future__ import annotations

import re
from pathlib import Path

import sitescore.model

FORBIDDEN = {
    r"\bDataStore\b": "construct or use the store directly",
    r"\bread_parquet\b|\bread_csv\b|\bread_file\b": "read files directly",
    r"\bPROCESSED_DIR\b|\braw_dir\b": "reach into data folders",
    r"\bopen\(": "open files",
    r"from sitescore\.pipeline|import sitescore\.pipeline": "import the pipeline",
}


def test_model_reads_data_only_through_asof_view():
    model_dir = Path(sitescore.model.__file__).parent
    problems = []
    for path in model_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pattern, what in FORBIDDEN.items():
            if re.search(pattern, text):
                problems.append(f"{path.name} may not {what} ({pattern})")
    assert not problems, "\n".join(problems)
