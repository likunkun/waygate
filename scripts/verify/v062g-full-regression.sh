#!/usr/bin/env bash
set -euo pipefail

python3 -m pytest workflow_controller/tests -q
