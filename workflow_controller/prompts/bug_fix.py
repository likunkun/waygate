from __future__ import annotations

from pathlib import Path
from typing import Any


def _render_bug_fix_prompt(state: dict[str, Any], body_path: Path) -> str:
    feedback = state.get('finalAcceptanceDefectFeedback') or state.get('finalAcceptanceRejectionFeedback') or ''
    bug_gate = state.get('bugFixGateFeedback') or ''
    return f"""Fix the final acceptance defect under the already-approved requirements only.

Write a JSON result to this exact file:
{body_path}

The JSON object must include:
- status: "ok", "failed", or "escalate_unit_plan"
- root_cause: object with classification, summary, and route ("bug_fix" or "unit_plan")
- changed_files: array of changed file paths
- regression: object with commands and evidence

Do not add, remove, weaken, or reinterpret approved requirements or acceptance criteria.
If the root cause is a unit-plan gap or architecture issue, set status to "escalate_unit_plan" and root_cause.route to "unit_plan".
Add or update regression tests or provide manual evidence.

Final acceptance defect feedback:
```md
{feedback}
```

Approved Bug Fix Gate:
```md
{bug_gate}
```
"""
