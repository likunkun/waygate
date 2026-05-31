from __future__ import annotations

import json
from pathlib import Path

import pytest

import workflow_controller.steps.builder as builder_module
from workflow_controller.gates.validators import validate_unit_plan_handoff_continuity
from workflow_controller.rrc_controller import RalphRefinerController
from workflow_controller.steps.builder import run_verifier


def _case(case_id: str, command: str = 'bash scripts/verify/unit.sh') -> dict[str, object]:
    return {
        'id': case_id,
        'acceptance_criterion': 'AC-1',
        'layer': 'functional',
        'command': command,
        'expected': 'ready artifact is produced and verified',
    }


def test_unit_plan_handoff_continuity_allows_single_unit_without_handoff() -> None:
    validate_unit_plan_handoff_continuity({
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'done_when': ['TC-UNIT exits 0 and AC-1 is covered'],
                'test_cases': [_case('TC-UNIT')],
                'verification_commands': ['bash scripts/verify/unit.sh'],
            }
        ]
    })


def test_unit_plan_handoff_continuity_rejects_vague_two_unit_handoff() -> None:
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'done_when': ['environment ready'],
                'test_cases': [_case('TC-U1-READY', 'bash scripts/verify/u1.sh')],
                'verification_commands': ['bash scripts/verify/u1.sh'],
                'handoff': {
                    'human_summary': 'environment ready',
                    'produces': [],
                    'requires': [],
                    'ready_checks': [],
                    'evidence_artifacts': [],
                },
            },
            {
                'id': 'unit-02',
                'passes': False,
                'depends_on': ['unit-01'],
                'done_when': ['uses previous environment'],
                'test_cases': [_case('TC-U2-CONSUME', 'bash scripts/verify/u2.sh')],
                'verification_commands': ['bash scripts/verify/u2.sh'],
                'handoff': {
                    'human_summary': 'consume environment ready',
                    'produces': [],
                    'requires': ['environment ready'],
                    'ready_checks': ['TC-U2-CONSUME'],
                    'evidence_artifacts': [],
                },
            },
        ]
    }

    with pytest.raises(ValueError) as excinfo:
        validate_unit_plan_handoff_continuity(state)

    message = str(excinfo.value)
    assert 'unit plan handoff continuity is incomplete' in message
    assert 'human_summary is vague' in message
    assert 'unit-02 requires environment ready but dependency unit-01 does not produce it' in message


def test_unit_plan_handoff_continuity_accepts_matched_producer_consumer_handoff() -> None:
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'done_when': [
                    'TC-U1-EXPORT exits 0 and artifacts/unit-01/export.json is listed in handoff evidence'
                ],
                'test_cases': [_case('TC-U1-EXPORT', 'bash scripts/verify/u1-export.sh')],
                'verification_commands': ['bash scripts/verify/u1-export.sh'],
                'handoff': {
                    'human_summary': 'unit-01 exports a normalized catalog JSON for unit-02 importer tests',
                    'produces': ['normalized catalog JSON'],
                    'requires': [],
                    'ready_checks': ['TC-U1-EXPORT'],
                    'evidence_artifacts': ['export.json'],
                },
            },
            {
                'id': 'unit-02',
                'passes': False,
                'depends_on': ['unit-01'],
                'done_when': ['TC-U2-IMPORT consumes normalized catalog JSON from unit-01 and exits 0'],
                'test_cases': [_case('TC-U2-IMPORT', 'bash scripts/verify/u2-import.sh')],
                'verification_commands': ['bash scripts/verify/u2-import.sh'],
                'handoff': {
                    'human_summary': 'unit-02 imports the normalized catalog JSON produced by unit-01',
                    'produces': ['catalog import result'],
                    'requires': ['normalized catalog JSON'],
                    'ready_checks': ['TC-U2-IMPORT'],
                    'evidence_artifacts': ['import-result.json'],
                },
            },
        ]
    }

    validate_unit_plan_handoff_continuity(state)


def test_unit_plan_handoff_continuity_requires_human_sections_for_multi_unit_gate(tmp_path: Path) -> None:
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'done_when': ['TC-U1-EXPORT exits 0 and export.json exists'],
                'test_cases': [_case('TC-U1-EXPORT', 'bash scripts/verify/u1-export.sh')],
                'verification_commands': ['bash scripts/verify/u1-export.sh'],
                'handoff': {
                    'human_summary': 'unit-01 exports normalized catalog JSON for unit-02 importer tests',
                    'produces': ['normalized catalog JSON'],
                    'requires': [],
                    'ready_checks': ['TC-U1-EXPORT'],
                    'evidence_artifacts': ['export.json'],
                },
            },
            {
                'id': 'unit-02',
                'passes': False,
                'depends_on': ['unit-01'],
                'done_when': ['TC-U2-IMPORT consumes normalized catalog JSON and exits 0'],
                'test_cases': [_case('TC-U2-IMPORT', 'bash scripts/verify/u2-import.sh')],
                'verification_commands': ['bash scripts/verify/u2-import.sh'],
                'handoff': {
                    'human_summary': 'unit-02 imports the normalized catalog JSON produced by unit-01',
                    'produces': ['catalog import result'],
                    'requires': ['normalized catalog JSON'],
                    'ready_checks': ['TC-U2-IMPORT'],
                    'evidence_artifacts': ['import-result.json'],
                },
            },
        ]
    }
    gate_path = tmp_path / 'unit-plan.md'
    gate_path.write_text(
        '## Test Case Matrix\n\n'
        '| Test Case | Command |\n'
        '| --- | --- |\n'
        '| TC-U1-EXPORT | bash scripts/verify/u1-export.sh |\n'
        '| TC-U2-IMPORT | bash scripts/verify/u2-import.sh |\n',
        encoding='utf-8',
    )

    with pytest.raises(ValueError) as excinfo:
        validate_unit_plan_handoff_continuity(state, unit_plan_path=gate_path)

    message = str(excinfo.value)
    assert 'Unit Plan missing `## 单元连贯性摘要`' in message
    assert 'Unit Plan missing `## Handoff Matrix`' in message

    gate_path.write_text(
        '## 单元连贯性摘要\n\n'
        'unit-01 exports normalized catalog JSON and unit-02 consumes it.\n\n'
        '## Handoff Matrix\n\n'
        '| Upstream Unit | Downstream Unit | Produced Artifacts / Readiness | Consumed Inputs | Evidence Path | Failure Route |\n'
        '| --- | --- | --- | --- | --- | --- |\n'
        '| unit-01 | unit-02 | normalized catalog JSON | normalized catalog JSON | artifacts/unit-01/handoff-evidence.json | revise Unit Plan |\n',
        encoding='utf-8',
    )

    validate_unit_plan_handoff_continuity(state, unit_plan_path=gate_path)


def test_unit_plan_handoff_continuity_accepts_split_multi_dependency_handoff() -> None:
    state = {
        'units': [
            {
                'id': 'unit-schema',
                'passes': False,
                'done_when': ['TC-SCHEMA exits 0 and schema.json exists'],
                'test_cases': [_case('TC-SCHEMA', 'bash scripts/verify/schema.sh')],
                'verification_commands': ['bash scripts/verify/schema.sh'],
                'handoff': {
                    'human_summary': 'unit-schema exports the canonical schema used by the import pipeline',
                    'produces': ['canonical schema JSON'],
                    'requires': [],
                    'ready_checks': ['TC-SCHEMA'],
                    'evidence_artifacts': ['schema.json'],
                },
            },
            {
                'id': 'unit-fixture',
                'passes': False,
                'done_when': ['TC-FIXTURE exits 0 and fixture.json exists'],
                'test_cases': [_case('TC-FIXTURE', 'bash scripts/verify/fixture.sh')],
                'verification_commands': ['bash scripts/verify/fixture.sh'],
                'handoff': {
                    'human_summary': 'unit-fixture exports the seeded fixture used by the import pipeline',
                    'produces': ['seed fixture JSON'],
                    'requires': [],
                    'ready_checks': ['TC-FIXTURE'],
                    'evidence_artifacts': ['fixture.json'],
                },
            },
            {
                'id': 'unit-import',
                'passes': False,
                'depends_on': ['unit-schema', 'unit-fixture'],
                'done_when': ['TC-IMPORT consumes schema and fixture handoffs then exits 0'],
                'test_cases': [_case('TC-IMPORT', 'bash scripts/verify/import.sh')],
                'verification_commands': ['bash scripts/verify/import.sh'],
                'handoff': {
                    'human_summary': 'unit-import consumes the canonical schema and seeded fixture from upstream units',
                    'produces': ['import verification report'],
                    'requires': ['canonical schema JSON', 'seed fixture JSON'],
                    'ready_checks': ['TC-IMPORT'],
                    'evidence_artifacts': ['import-report.json'],
                },
            },
        ]
    }

    validate_unit_plan_handoff_continuity(state)


@pytest.mark.parametrize(
    ('units', 'expected'),
    [
        (
            [
                {
                    'id': 'unit-01',
                    'passes': False,
                    'depends_on': ['unit-missing'],
                    'done_when': ['TC-U1 exits 0'],
                    'test_cases': [_case('TC-U1')],
                    'verification_commands': ['bash scripts/verify/unit.sh'],
                    'handoff': {
                        'human_summary': 'unit-01 consumes a concrete missing dependency artifact',
                        'produces': ['result'],
                        'requires': ['input'],
                        'ready_checks': ['TC-U1'],
                        'evidence_artifacts': ['result.json'],
                    },
                }
            ],
            'depends_on unknown unit unit-missing',
        ),
        (
            [
                {
                    'id': 'unit-01',
                    'passes': False,
                    'depends_on': ['unit-02'],
                    'done_when': ['TC-U1 exits 0'],
                    'test_cases': [_case('TC-U1', 'bash scripts/verify/u1.sh')],
                    'verification_commands': ['bash scripts/verify/u1.sh'],
                    'handoff': {
                        'human_summary': 'unit-01 consumes unit-02 schema and writes report output',
                        'produces': ['report output'],
                        'requires': ['schema'],
                        'ready_checks': ['TC-U1'],
                        'evidence_artifacts': ['report.json'],
                    },
                },
                {
                    'id': 'unit-02',
                    'passes': False,
                    'depends_on': ['unit-01'],
                    'done_when': ['TC-U2 exits 0'],
                    'test_cases': [_case('TC-U2', 'bash scripts/verify/u2.sh')],
                    'verification_commands': ['bash scripts/verify/u2.sh'],
                    'handoff': {
                        'human_summary': 'unit-02 consumes report output and writes schema',
                        'produces': ['schema'],
                        'requires': ['report output'],
                        'ready_checks': ['TC-U2'],
                        'evidence_artifacts': ['schema.json'],
                    },
                },
            ],
            'circular dependency',
        ),
        (
            [
                {
                    'id': 'unit-01',
                    'passes': False,
                    'done_when': ['TC-U1 exits 0 and export.json exists'],
                    'test_cases': [_case('TC-U1', 'bash scripts/verify/u1.sh')],
                    'verification_commands': ['bash scripts/verify/u1.sh'],
                    'handoff': {
                        'human_summary': 'unit-01 produces export JSON for downstream importer',
                        'produces': ['export JSON'],
                        'requires': [],
                        'ready_checks': ['manual note only'],
                        'evidence_artifacts': ['export.json'],
                    },
                },
                {
                    'id': 'unit-02',
                    'passes': False,
                    'depends_on': ['unit-01'],
                    'done_when': ['TC-U2 exits 0'],
                    'test_cases': [_case('TC-U2', 'bash scripts/verify/u2.sh')],
                    'verification_commands': ['bash scripts/verify/u2.sh'],
                    'handoff': {
                        'human_summary': 'unit-02 consumes export JSON from unit-01',
                        'produces': ['import result'],
                        'requires': ['export JSON'],
                        'ready_checks': ['TC-U2'],
                        'evidence_artifacts': ['import-result.json'],
                    },
                },
            ],
            'ready_check manual note only is not mapped',
        ),
    ],
)
def test_unit_plan_handoff_continuity_rejects_dependency_gaps(
    units: list[dict[str, object]],
    expected: str,
) -> None:
    with pytest.raises(ValueError) as excinfo:
        validate_unit_plan_handoff_continuity({'units': units})

    assert expected in str(excinfo.value)


def test_run_verifier_writes_failed_handoff_evidence_when_producer_artifact_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unit_dir = tmp_path / 'artifacts' / 'unit-01'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    command = 'bash scripts/verify/u1-export.sh'
    state = {
        'currentUnitId': 'unit-01',
        'workspacePath': str(workspace),
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [_case('TC-U1-EXPORT', command)],
                'verification_commands': [command],
                'handoff': {
                    'human_summary': 'unit-01 exports a normalized catalog JSON for unit-02 importer tests',
                    'produces': ['normalized catalog JSON'],
                    'requires': [],
                    'ready_checks': ['TC-U1-EXPORT'],
                    'evidence_artifacts': ['export.json'],
                },
            }
        ],
    }

    monkeypatch.setattr(
        builder_module,
        'run_verification_commands',
        lambda state, workspace, progress_callback=None: [
            {'command': command, 'ok': True, 'returncode': 0, 'stdout': 'passed', 'stderr': ''}
        ],
    )

    result = run_verifier(state, unit_dir)

    assert result.summary == 'verification failed'
    evidence = json.loads((unit_dir / 'handoff-evidence.json').read_text(encoding='utf-8'))
    assert evidence['unit_id'] == 'unit-01'
    assert evidence['passed'] is False
    assert evidence['issues'][0]['type'] == 'unit_handoff_evidence_missing'


def test_run_verifier_writes_passed_handoff_evidence_for_producer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unit_dir = tmp_path / 'artifacts' / 'unit-01'
    unit_dir.mkdir(parents=True)
    (unit_dir / 'export.json').write_text('{"ok": true}\n', encoding='utf-8')
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    command = 'bash scripts/verify/u1-export.sh'
    state = {
        'currentUnitId': 'unit-01',
        'workspacePath': str(workspace),
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [_case('TC-U1-EXPORT', command)],
                'verification_commands': [command],
                'handoff': {
                    'human_summary': 'unit-01 exports a normalized catalog JSON for unit-02 importer tests',
                    'produces': ['normalized catalog JSON'],
                    'requires': [],
                    'ready_checks': ['TC-U1-EXPORT'],
                    'evidence_artifacts': ['export.json'],
                },
            }
        ],
    }

    monkeypatch.setattr(
        builder_module,
        'run_verification_commands',
        lambda state, workspace, progress_callback=None: [
            {'command': command, 'ok': True, 'returncode': 0, 'stdout': 'passed', 'stderr': ''}
        ],
    )

    result = run_verifier(state, unit_dir)

    assert result.summary == 'verification passed'
    evidence = json.loads((unit_dir / 'handoff-evidence.json').read_text(encoding='utf-8'))
    assert evidence['passed'] is True
    assert evidence['produces'] == ['normalized catalog JSON']
    assert evidence['evidence_artifacts'][0]['exists'] is True


def test_downstream_builder_blocks_when_dependency_handoff_evidence_is_missing(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'handoff',
            'currentUnitId': 'unit-02',
            'currentStep': 'EXECUTE_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01', 'unit-02'], 'status': 'partial'},
            ],
            'units': [
                {
                    'id': 'unit-01',
                    'name': 'Producer',
                    'passes': True,
                    'handoff': {
                        'human_summary': 'unit-01 exports a normalized catalog JSON for unit-02 importer tests',
                        'produces': ['normalized catalog JSON'],
                        'requires': [],
                        'ready_checks': ['TC-U1-EXPORT'],
                        'evidence_artifacts': ['export.json'],
                    },
                },
                {
                    'id': 'unit-02',
                    'name': 'Consumer',
                    'passes': False,
                    'depends_on': ['unit-01'],
                    'handoff': {
                        'human_summary': 'unit-02 consumes the normalized catalog JSON from unit-01',
                        'produces': ['catalog import result'],
                        'requires': ['normalized catalog JSON'],
                        'ready_checks': ['TC-U2-IMPORT'],
                        'evidence_artifacts': ['import-result.json'],
                    },
                },
            ],
        },
        force=True,
    )

    state = controller.run_once()

    assert state['status'] == 'blocked'
    assert state['currentStep'] == 'EXECUTE_UNIT'
    assert state['blockedContext']['category'] == 'unit_handoff'
    assert 'unit-01' in state['blockedReason']
    assert 'handoff-evidence.json' in state['blockedReason']


def test_downstream_builder_handoff_preflight_accepts_split_multi_dependency_evidence(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'handoff',
            'currentUnitId': 'unit-import',
            'currentStep': 'EXECUTE_UNIT',
            'status': 'active',
            'units': [
                {
                    'id': 'unit-schema',
                    'passes': True,
                    'handoff': {
                        'human_summary': 'unit-schema exports the canonical schema used by the import pipeline',
                        'produces': ['canonical schema JSON'],
                        'requires': [],
                        'ready_checks': ['TC-SCHEMA'],
                        'evidence_artifacts': ['schema.json'],
                    },
                },
                {
                    'id': 'unit-fixture',
                    'passes': True,
                    'handoff': {
                        'human_summary': 'unit-fixture exports the seeded fixture used by the import pipeline',
                        'produces': ['seed fixture JSON'],
                        'requires': [],
                        'ready_checks': ['TC-FIXTURE'],
                        'evidence_artifacts': ['fixture.json'],
                    },
                },
                {
                    'id': 'unit-import',
                    'passes': False,
                    'depends_on': ['unit-schema', 'unit-fixture'],
                    'handoff': {
                        'human_summary': 'unit-import consumes the canonical schema and seeded fixture from upstream units',
                        'produces': ['import verification report'],
                        'requires': ['canonical schema JSON', 'seed fixture JSON'],
                        'ready_checks': ['TC-IMPORT'],
                        'evidence_artifacts': ['import-report.json'],
                    },
                },
            ],
        },
        force=True,
    )
    for unit_id, produces in [
        ('unit-schema', ['canonical schema JSON']),
        ('unit-fixture', ['seed fixture JSON']),
    ]:
        unit_dir = controller.artifacts_dir / unit_id
        unit_dir.mkdir(parents=True)
        (unit_dir / 'handoff-evidence.json').write_text(
            json.dumps({'passed': True, 'produces': produces, 'issues': []}),
            encoding='utf-8',
        )

    assert controller._unit_handoff_blocked_context(controller.store.load_state()) is None
