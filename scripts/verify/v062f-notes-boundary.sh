#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
python3 -m pytest workflow_controller/tests/test_v062f_review_control.py -q -k 'approval_notes or unit_plan_approval_notes'
