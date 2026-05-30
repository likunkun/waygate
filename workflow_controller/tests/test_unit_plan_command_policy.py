from __future__ import annotations

import pytest

from workflow_controller.gates.validators import validate_unit_plan_script_entry_commands


def test_unit_plan_command_policy_rejects_inline_bash_pipeline() -> None:
    command = 'bash -lc "printf foo | grep foo"'
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-AC1-PIPELINE',
                        'acceptance_criterion': 'AC-1',
                        'layer': 'functional',
                        'command': command,
                        'expected': 'stdout contains foo',
                    }
                ],
                'verification_commands': [command],
            }
        ]
    }

    with pytest.raises(ValueError) as excinfo:
        validate_unit_plan_script_entry_commands(state)

    message = str(excinfo.value)
    assert 'TC-AC1-PIPELINE' in message
    assert 'write the command into a script file' in message


def test_unit_plan_command_policy_allows_bash_script_entrypoint() -> None:
    command = 'bash scripts/verify/tc-ac1-pipeline.sh'
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-AC1-PIPELINE',
                        'acceptance_criterion': 'AC-1',
                        'layer': 'functional',
                        'command': command,
                        'expected': 'stdout contains foo',
                    }
                ],
                'verification_commands': [command],
            }
        ]
    }

    validate_unit_plan_script_entry_commands(state)


def test_unit_plan_command_policy_allows_direct_verify_script_entrypoint() -> None:
    command = './scripts/verify/tc-ac1-pipeline.sh'
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-AC1-DIRECT-SCRIPT',
                        'acceptance_criterion': 'AC-1',
                        'layer': 'functional',
                        'command': command,
                        'expected': 'script verifies behavior',
                    }
                ],
                'verification_commands': [command],
            }
        ]
    }

    validate_unit_plan_script_entry_commands(state)


def test_unit_plan_command_policy_rejects_quoted_python_code_string() -> None:
    command = 'python -c "from pathlib import Path; print(Path.cwd())"'
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-PYTHON-C',
                        'acceptance_criterion': 'AC-1',
                        'layer': 'functional',
                        'command': command,
                        'expected': 'prints cwd',
                    }
                ],
                'verification_commands': [command],
            }
        ]
    }

    with pytest.raises(ValueError) as excinfo:
        validate_unit_plan_script_entry_commands(state)

    assert 'TC-PYTHON-C' in str(excinfo.value)
    assert 'write the command into a script file' in str(excinfo.value)


def test_unit_plan_command_policy_rejects_direct_pytest_invocation() -> None:
    command = 'python3 -m pytest workflow_controller/tests -q'
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-DIRECT-PYTEST',
                        'acceptance_criterion': 'AC-1',
                        'layer': 'functional',
                        'command': command,
                        'expected': 'pytest suite passes',
                    }
                ],
                'verification_commands': [command],
            }
        ]
    }

    with pytest.raises(ValueError) as excinfo:
        validate_unit_plan_script_entry_commands(state)

    assert 'TC-DIRECT-PYTEST' in str(excinfo.value)


def test_unit_plan_command_policy_allows_python_script_entrypoint() -> None:
    command = 'python3 scripts/verify/tc_ac1.py'
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-PYTHON-SCRIPT',
                        'acceptance_criterion': 'AC-1',
                        'layer': 'functional',
                        'command': command,
                        'expected': 'script verifies behavior',
                    }
                ],
                'verification_commands': [command],
            }
        ]
    }

    validate_unit_plan_script_entry_commands(state)


def test_unit_plan_command_policy_allows_python_alias_script_entrypoint() -> None:
    command = 'python scripts/verify/tc_ac1.py'
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-PYTHON-ALIAS-SCRIPT',
                        'acceptance_criterion': 'AC-1',
                        'layer': 'functional',
                        'command': command,
                        'expected': 'script verifies behavior',
                    }
                ],
                'verification_commands': [command],
            }
        ]
    }

    validate_unit_plan_script_entry_commands(state)


def test_unit_plan_command_policy_allows_direct_python_script_entrypoint() -> None:
    command = './scripts/verify/tc_ac1.py'
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-PYTHON-DIRECT-SCRIPT',
                        'acceptance_criterion': 'AC-1',
                        'layer': 'functional',
                        'command': command,
                        'expected': 'script verifies behavior',
                    }
                ],
                'verification_commands': [command],
            }
        ]
    }

    validate_unit_plan_script_entry_commands(state)


def test_unit_plan_command_policy_rejects_unquoted_shell_pipeline() -> None:
    command = 'printf foo | grep foo'
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-UNQUOTED-PIPELINE',
                        'acceptance_criterion': 'AC-1',
                        'layer': 'functional',
                        'command': command,
                        'expected': 'stdout contains foo',
                    }
                ],
                'verification_commands': [command],
            }
        ]
    }

    with pytest.raises(ValueError) as excinfo:
        validate_unit_plan_script_entry_commands(state)

    assert 'TC-UNQUOTED-PIPELINE' in str(excinfo.value)
