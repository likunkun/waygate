from __future__ import annotations

from pathlib import Path
from typing import Any

from workflow_controller.steps._common import StepResult


def run_bug_fix(state: dict[str, Any], unit_dir: Path, dry_run: bool = False) -> StepResult:
    raise NotImplementedError('bug_fix step is not yet implemented (V0.5)')
