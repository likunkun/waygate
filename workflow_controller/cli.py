from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from workflow_controller.rrc_controller import (
    COLOR_MODES,
    DEFAULT_MAX_AUTOMATIC_STEPS,
    RalphRefinerController,
)
from workflow_controller.state_machine.actions import compute_next_allowed_action


def _build_strategist_overrides(args: argparse.Namespace) -> dict[str, Any] | None:
    enabled = getattr(args, 'test_strategist', False)
    command = getattr(args, 'test_strategist_command', None)
    raw_env = getattr(args, 'test_strategist_env', None) or []
    if not enabled and not command and not raw_env:
        return None
    overrides: dict[str, Any] = {'testStrategistEnabled': True}
    if command or raw_env:
        role_runner: dict[str, Any] = {'runner': 'subprocess'}
        if command:
            role_runner['command'] = command
        if raw_env:
            env: dict[str, str] = {}
            for pair in raw_env:
                k, _, v = pair.partition('=')
                env[k] = v
            role_runner['env'] = env
        overrides['roleRunners'] = {'test_strategist': role_runner}
    return overrides


def render_status_line(state: dict[str, Any]) -> str:
    next_action = state.get('nextAction') or compute_next_allowed_action(state)
    return (
        f"currentStep={state.get('currentStep')} "
        f"status={state.get('status')} "
        f"nextAction={next_action}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Ralph Refiner Controller', allow_abbrev=False)
    subparsers = parser.add_subparsers(dest='command', required=True)

    init_parser = subparsers.add_parser(
        'init',
        help='Initialize a new session state directory',
        allow_abbrev=False,
    )
    init_parser.add_argument('--state-dir', default='.plan-ralph', help='Directory containing session.json and artifacts/')
    init_parser.add_argument('--force', action='store_true', help='Overwrite an existing session.json')
    init_parser.add_argument('--auto-approve', action='store_true', help='Auto-generate approval artifacts during init and runtime')
    init_parser.add_argument('--workspace-dir', default=None, help='Workspace containing .plan-ralph/session.json')
    init_parser.add_argument('--from-ralph', action='store_true', help='Initialize controller state from an existing Ralph session')
    init_parser.add_argument('--agent', default='claude', help='Agent command used by the real builder runtime')
    init_parser.add_argument('--runner', default='subprocess', help='Agent runner backend: subprocess or tmux-claude')
    init_parser.add_argument('--tmux-target', default=None, help='tmux pane target for --runner tmux-claude, for example 1.2')
    init_parser.add_argument('--target', default=None, help='Target Ralph step id or acceptance label to run')
    init_parser.add_argument('--unsafe-skip-human-gates', action='store_true', help='Bypass Markdown human gates and write an audit event')
    init_parser.add_argument('--test-strategist', action='store_true', default=False, help='Enable Test Strategist for Unit Plan draft')
    init_parser.add_argument('--test-strategist-command', default=None, help='Override Test Strategist runner command')
    init_parser.add_argument('--test-strategist-env', action='append', metavar='KEY=VALUE', dest='test_strategist_env', help='Inject env var into Test Strategist subprocess only (repeatable)')

    status_parser = subparsers.add_parser(
        'status',
        help='Show current workflow status',
        allow_abbrev=False,
    )
    status_parser.add_argument('--state-dir', default='.plan-ralph', help='Directory containing session.json and artifacts/')
    status_parser.add_argument('--auto-approve', action='store_true', help='Reflect auto-approve mode in status/runtime decisions')

    approve_parser = subparsers.add_parser(
        'approve',
        help='Approve a Markdown human gate after manual review',
        allow_abbrev=False,
    )
    approve_parser.add_argument('--state-dir', default='.plan-ralph', help='Directory containing session.json and approvals/')
    approve_parser.add_argument(
        '--gate',
        required=True,
        choices=['requirements', 'unit-plan', 'final-acceptance'],
        help='Markdown human gate to approve',
    )
    approve_parser.add_argument('--actor', default='human', help='Name recorded in the Human Confirmation block')

    reject_parser = subparsers.add_parser(
        'reject',
        help='Reject the final acceptance gate and route feedback back into the workflow',
        allow_abbrev=False,
    )
    reject_parser.add_argument('--state-dir', default='.plan-ralph', help='Directory containing session.json and approvals/')

    revise_parser = subparsers.add_parser(
        'revise',
        help='Regenerate a Markdown gate from human feedback in the current draft',
        allow_abbrev=False,
    )
    revise_parser.add_argument('--state-dir', default='.plan-ralph', help='Directory containing session.json and approvals/')
    revise_parser.add_argument(
        '--gate',
        required=True,
        choices=['requirements', 'unit-plan'],
        help='Markdown human gate to revise',
    )

    migrate_parser = subparsers.add_parser(
        'migrate',
        help='Migrate an existing state directory to the latest gate format',
        allow_abbrev=False,
    )
    migrate_parser.add_argument('--state-dir', default='.plan-ralph', help='Directory containing session.json and approvals/')

    start_parser = subparsers.add_parser(
        'start',
        help='Initialize the workflow if needed, then continuously drive it',
        allow_abbrev=False,
    )
    start_parser.add_argument('--state-dir', default='.plan-ralph', help='Directory containing session.json and artifacts/')
    start_parser.add_argument('--force', action='store_true', help='Reinitialize an existing session before driving')
    start_parser.add_argument('--dry-run', action='store_true', help='Simulate step execution by writing mock artifacts')
    start_parser.add_argument('--max-steps', type=int, default=DEFAULT_MAX_AUTOMATIC_STEPS, help='Maximum automatic steps to run before stopping')
    start_parser.add_argument('--auto-approve', action='store_true', help='Auto-generate low-risk approval artifacts during runtime')
    start_parser.add_argument('--workspace-dir', default=None, help='Workspace containing .plan-ralph/session.json')
    start_parser.add_argument('--from-ralph', action='store_true', help='Initialize controller state from an existing Ralph session')
    start_parser.add_argument('--agent', default=None, help='Agent command used by the real builder runtime')
    start_parser.add_argument('--runner', default=None, help='Agent runner backend: subprocess or tmux-claude')
    start_parser.add_argument('--tmux-target', default=None, help='tmux pane target for --runner tmux-claude, for example 1.2')
    start_parser.add_argument('--target', default=None, help='Target Ralph step id or acceptance label to run')
    start_parser.add_argument('--actor', default='human', help='Name recorded when approving a Human Confirmation gate')
    start_parser.add_argument('--unsafe-skip-human-gates', action='store_true', help='Bypass Markdown human gates and write an audit event')
    start_parser.add_argument('--plannotator-command', default='plannotator', help='Command used for Plannotator-assisted human gate review')
    start_parser.add_argument('--plannotator-port', type=int, default=20000, help='Port exported to Plannotator as PLANNOTATOR_PORT')
    start_parser.add_argument('--verbose', action='store_true', help='Show raw per-step progress and execution lines')
    start_parser.add_argument('--color', choices=COLOR_MODES, default='auto', help='Color compact output: auto, always, or never')
    start_parser.add_argument('--test-strategist', action='store_true', default=False, help='Enable Test Strategist for Unit Plan draft')
    start_parser.add_argument('--test-strategist-command', default=None, help='Override Test Strategist runner command')
    start_parser.add_argument('--test-strategist-env', action='append', metavar='KEY=VALUE', dest='test_strategist_env', help='Inject env var into Test Strategist subprocess only (repeatable)')

    drive_parser = subparsers.add_parser(
        'drive',
        help='Continuously drive the workflow and stop only at human confirmation gates',
        allow_abbrev=False,
    )
    drive_parser.add_argument('--state-dir', default='.plan-ralph', help='Directory containing session.json and artifacts/')
    drive_parser.add_argument('--dry-run', action='store_true', help='Simulate step execution by writing mock artifacts')
    drive_parser.add_argument('--max-steps', type=int, default=DEFAULT_MAX_AUTOMATIC_STEPS, help='Maximum automatic steps to run before stopping')
    drive_parser.add_argument('--auto-approve', action='store_true', help='Auto-generate low-risk approval artifacts during runtime')
    drive_parser.add_argument('--workspace-dir', default=None, help='Override workspace path stored in session.json')
    drive_parser.add_argument('--agent', default=None, help='Override agent command used by the builder runtime')
    drive_parser.add_argument('--runner', default=None, help='Override agent runner backend: subprocess or tmux-claude')
    drive_parser.add_argument('--tmux-target', default=None, help='Override tmux pane target for --runner tmux-claude')
    drive_parser.add_argument('--target', default=None, help='Target Ralph step id or acceptance label to run')
    drive_parser.add_argument('--actor', default='human', help='Name recorded when approving a Human Confirmation gate')
    drive_parser.add_argument('--unsafe-skip-human-gates', action='store_true', help='Bypass Markdown human gates and write an audit event')
    drive_parser.add_argument('--plannotator-command', default='plannotator', help='Command used for Plannotator-assisted human gate review')
    drive_parser.add_argument('--plannotator-port', type=int, default=20000, help='Port exported to Plannotator as PLANNOTATOR_PORT')
    drive_parser.add_argument('--verbose', action='store_true', help='Show raw per-step progress and execution lines')
    drive_parser.add_argument('--color', choices=COLOR_MODES, default='auto', help='Color compact output: auto, always, or never')

    run_parser = subparsers.add_parser(
        'run',
        help='Advance the workflow by one step or until terminal state',
        allow_abbrev=False,
    )
    run_parser.add_argument('--state-dir', default='.plan-ralph', help='Directory containing session.json and artifacts/')
    run_parser.add_argument('--dry-run', action='store_true', help='Simulate step execution by writing mock artifacts')
    run_parser.add_argument('--until-done', action='store_true', help='Continue running until done/blocked/failed')
    run_parser.add_argument('--max-steps', type=int, default=DEFAULT_MAX_AUTOMATIC_STEPS, help='Maximum steps to run in --until-done mode')
    run_parser.add_argument('--auto-approve', action='store_true', help='Auto-generate approval artifacts during runtime')
    run_parser.add_argument('--workspace-dir', default=None, help='Override workspace path stored in session.json')
    run_parser.add_argument('--agent', default=None, help='Override agent command used by the builder runtime')
    run_parser.add_argument('--runner', default=None, help='Override agent runner backend: subprocess or tmux-claude')
    run_parser.add_argument('--tmux-target', default=None, help='Override tmux pane target for --runner tmux-claude')
    run_parser.add_argument('--target', default=None, help='Target Ralph step id or acceptance label to run')
    run_parser.add_argument('--unsafe-skip-human-gates', action='store_true', help='Bypass Markdown human gates and write an audit event')

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    controller = RalphRefinerController(
        state_dir=Path(args.state_dir),
        dry_run=getattr(args, 'dry_run', False),
        auto_approve=getattr(args, 'auto_approve', False),
        workspace_dir=Path(args.workspace_dir) if getattr(args, 'workspace_dir', None) else None,
        agent_command=getattr(args, 'agent', None),
        agent_runner=getattr(args, 'runner', None),
        tmux_target=getattr(args, 'tmux_target', None),
        target=getattr(args, 'target', None),
        unsafe_skip_human_gates=getattr(args, 'unsafe_skip_human_gates', False),
        plannotator_command=getattr(args, 'plannotator_command', 'plannotator'),
        plannotator_port=getattr(args, 'plannotator_port', 20000),
    )

    if args.command == 'init':
        strategist_overrides = _build_strategist_overrides(args)
        state = controller.init_state(force=args.force, from_ralph=args.from_ralph, strategist_overrides=strategist_overrides)
        print(render_status_line(state))
        return

    if args.command == 'status':
        state = controller.get_status()
        print(render_status_line(state))
        return

    if args.command == 'approve':
        try:
            gate_path = controller.approve_human_gate(args.gate, actor=args.actor)
        except Exception as exc:
            print(f'error: {exc}', file=sys.stderr)
            raise SystemExit(1) from None
        print(f'gate={args.gate} status=approved path={gate_path}')
        return

    if args.command == 'reject':
        try:
            gate_path = controller.reject_final_acceptance_gate()
        except Exception as exc:
            print(f'error: {exc}', file=sys.stderr)
            raise SystemExit(1) from None
        print(f'gate=final-acceptance status=rejected path={gate_path}')
        return

    if args.command == 'revise':
        try:
            gate_path = controller.revise_human_gate(args.gate)
        except Exception as exc:
            print(f'error: {exc}', file=sys.stderr)
            raise SystemExit(1) from None
        print(f'gate={args.gate} status=revised path={gate_path}')
        return

    if args.command == 'migrate':
        try:
            state = controller.migrate_state()
        except Exception as exc:
            print(f'error: {exc}', file=sys.stderr)
            raise SystemExit(1) from None
        paths = ','.join(state.get('migratedPaths') or [])
        print(f'status=migrated paths={paths}')
        return

    if args.command == 'start':
        try:
            controller.start(
                force=args.force,
                from_ralph=args.from_ralph,
                max_steps=args.max_steps,
                verbose=args.verbose,
                color_mode=args.color,
                actor=args.actor,
                strategist_overrides=_build_strategist_overrides(args),
            )
        except Exception as exc:
            print(f'error: {exc}', file=sys.stderr)
            raise SystemExit(1) from None
        return

    if args.command == 'drive':
        try:
            controller.drive(max_steps=args.max_steps, verbose=args.verbose, color_mode=args.color, actor=args.actor)
        except Exception as exc:
            print(f'error: {exc}', file=sys.stderr)
            raise SystemExit(1) from None
        return

    if args.command == 'run':
        try:
            state = controller.run_until_done(max_steps=args.max_steps) if args.until_done else controller.run_once()
        except Exception as exc:
            print(f'error: {exc}', file=sys.stderr)
            raise SystemExit(1) from None
        print(render_status_line(state))
        return

    raise ValueError(f'Unknown command: {args.command}')


if __name__ == '__main__':
    main()
