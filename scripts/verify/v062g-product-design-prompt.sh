#!/usr/bin/env bash
set -euo pipefail

python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q \
  -k 'product_design_prompt_contract or product_design_prompt_no_spec or product_design_prompt_supported_spec or product_design_prompt_backend_only or product_design_prompt_requires_manifest_contract_for_required_prototype'
