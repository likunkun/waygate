#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
python3 -m pytest workflow_controller/tests -q
git diff --check
