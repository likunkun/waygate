#!/usr/bin/env bash
set -euo pipefail

# Historical script name retained for existing Unit Plan command references.
# The annotation tmux runtime has been removed; these tests prove tmux/env
# context is ignored and annotation stays on the subprocess path.
export WAYGATE_ANNOTATION_TMUX=1

python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q \
  -k 'annotation_tmux_env_is_ignored_and_uses_subprocess_without_tmux_commands or controller_annotation_uses_subprocess_and_does_not_record_temp_pane or opencode_annotation_uses_configured_subprocess_command_when_tmux_env_is_set or custom_annotation_command_expands_args_through_subprocess_when_tmux_env_is_set'

python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q \
  -k 'tmux_target or tmux_codex or tmux_claude'
