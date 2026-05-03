from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_STATE_DIR = Path('.plan-ralph')
DEFAULT_SESSION_PATH = DEFAULT_STATE_DIR / 'session.json'
DEFAULT_EVENTS_PATH = DEFAULT_STATE_DIR / 'events.jsonl'


@dataclass
class StateStore:
    session_path: Path = DEFAULT_SESSION_PATH
    events_path: Path = DEFAULT_EVENTS_PATH

    def ensure_layout(self) -> None:
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.events_path.exists():
            self.events_path.write_text('', encoding='utf-8')

    def load_state(self) -> dict[str, Any]:
        self.ensure_layout()
        if not self.session_path.exists():
            raise FileNotFoundError(f'Session file not found: {self.session_path}')
        return json.loads(self.session_path.read_text(encoding='utf-8'))

    def save_state(self, state: dict[str, Any]) -> None:
        self.ensure_layout()
        state = dict(state)
        state['updatedAt'] = utc_now_iso()
        tmp_path = self.session_path.with_suffix('.json.tmp')
        tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp_path.replace(self.session_path)

    def append_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.ensure_layout()
        record = {
            'timestamp': utc_now_iso(),
            'type': event_type,
            'payload': payload,
        }
        with self.events_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
