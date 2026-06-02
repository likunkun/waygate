#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
python3 workflow_controller/tests/v062f_review_surface_e2e.py
