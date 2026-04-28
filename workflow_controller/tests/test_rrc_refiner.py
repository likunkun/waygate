from __future__ import annotations

import json
from pathlib import Path

from workflow_controller.rrc_steps import run_refiner


def test_run_refiner_generates_refinement_summary_from_changed_files(tmp_path: Path) -> None:
    unit_dir = tmp_path / 'artifacts' / 'unit-01'
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / 'changed-files.txt').write_text('src/login.py\ntests/test_login.py\n', encoding='utf-8')

    state = {'currentUnitId': 'unit-01'}
    result = run_refiner(state, unit_dir, dry_run=False)

    assert result.summary == 'refinement complete'
    payload = json.loads((unit_dir / 'refinement-summary.json').read_text(encoding='utf-8'))
    assert payload['unit_id'] == 'unit-01'
    assert payload['status'] == 'ok'
    assert payload['changed_files'] == ['src/login.py', 'tests/test_login.py']
