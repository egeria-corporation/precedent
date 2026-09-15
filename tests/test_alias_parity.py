"""The alias table exists twice, so this fails if the two copies drift.

`src/precedent/data/passthrough_aliases.yaml` is hand-maintained and is the source of
truth. The Worker cannot read a file or parse YAML at runtime, so it ships a generated
TypeScript module. Two hand-maintained copies of an entity table would drift, and the drift
would be invisible: the site and the tool would cluster the same auditor's spelling
differently and both would look right.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "awards" / "scripts" / "generate_aliases.py"
GENERATED = ROOT / "awards" / "src" / "analysis" / "aliases.ts"


def test_the_generated_alias_module_is_current() -> None:
    before = GENERATED.read_text(encoding="utf-8")
    subprocess.run([sys.executable, str(GENERATOR)], check=True, capture_output=True, cwd=ROOT)
    after = GENERATED.read_text(encoding="utf-8")
    assert before == after, (
        "awards/src/analysis/aliases.ts is out of date with passthrough_aliases.yaml. "
        "Run `python awards/scripts/generate_aliases.py` and commit the result."
    )


def test_every_canonical_entity_reaches_the_worker() -> None:
    import yaml

    rows = yaml.safe_load(
        (ROOT / "src" / "precedent" / "data" / "passthrough_aliases.yaml").read_text(
            encoding="utf-8"
        )
    )
    generated = GENERATED.read_text(encoding="utf-8")
    for row in rows:
        assert row["canonical"] in generated, f"{row['canonical']} missing from the Worker table"
        for alias in row.get("aliases") or []:
            assert alias in generated, f"alias {alias!r} missing from the Worker table"
