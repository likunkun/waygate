# Contributing to Waygate

[中文](CONTRIBUTING.zh-CN.md)

Thanks for taking the time to improve Waygate. This project is a workflow controller, so changes should preserve auditability, state safety, and explicit verification.

## Development Setup

```bash
git clone <repo-url>
cd workflow-controller
source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate
python -m pytest workflow_controller/tests -q
```

If you do not use the Hermes virtual environment, create a Python environment with the dependencies needed by the test suite.

## Before Sending a Pull Request

Please make sure:

- the change is scoped to one behavior or documentation goal;
- local controller state directories such as `.rrc-controller-*` are not committed;
- generated package output such as `dist/` and `.build/` is not committed;
- new behavior has regression tests where practical;
- documentation is updated when CLI behavior, workflow semantics, or artifacts change;
- the full test suite passes.

Recommended verification:

```bash
source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate
python -m pytest workflow_controller/tests -q
```

Packaging verification:

```bash
python -m pytest workflow_controller/tests/test_packaging.py -q
```

## Pull Request Notes

In the PR body, include:

- what changed;
- why it changed;
- how it was verified;
- any migration or compatibility notes;
- whether state artifacts or gate formats are affected.

## Code Style

Waygate favors small, explicit changes over broad refactors. Prefer existing local patterns, parsers, validators, and runner abstractions before adding new ones.

Do not store secrets in artifacts, logs, tests, or examples.
