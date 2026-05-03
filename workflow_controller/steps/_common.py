from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


@dataclass
class StepResult:
    approved: bool | None = None
    summary: str | None = None
    outputs: list[str] | None = None


class NotImplementedWorkflowStep(RuntimeError):
    pass


class TestStrategistBlocked(RuntimeError):
    def __init__(self, message: str, *, retry_count: int, gap_id: str | None = None) -> None:
        super().__init__(message)
        self.retry_count = retry_count
        self.gap_id = gap_id


class TestStrategistFallbackBlocked(RuntimeError):
    pass


def _approval_requested_by_state(state: dict[str, Any]) -> bool:
    return bool(state.get('autoApprove'))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def _write_json_result(path: Path, payload: dict[str, Any], summary: str) -> StepResult:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, payload)
    return StepResult(summary=summary, outputs=[path.name])


def _read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _issue(issue_type: str, message: str, severity: str = 'high') -> dict[str, str]:
    return {
        'severity': severity,
        'type': issue_type,
        'message': message,
    }


def _find_unit(state: dict[str, Any], unit_id: str | None) -> dict[str, Any]:
    for unit in state.get('units', []):
        if unit.get('id') == unit_id:
            return unit
    return {'id': unit_id or 'unknown-unit'}


def _find_objective_for_unit(state: dict[str, Any], unit_id: str | None) -> str | None:
    for item in state.get('objectiveCoverage', []):
        if unit_id in item.get('units', []):
            return item.get('objective')
    return None


def _tail_text(text: str, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    return f'... truncated ...\n{text[-max_chars:]}'
