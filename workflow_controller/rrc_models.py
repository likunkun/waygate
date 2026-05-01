from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoleConfig:
    role: str
    model_hint: str
    skill_hint: str


BUILDER = RoleConfig(
    role='builder',
    model_hint='strong-model',
    skill_hint='ralph-driven-delivery + test-driven-development',
)

UNIT_PLANNER = RoleConfig(
    role='unit_planner',
    model_hint='strong-planning-model',
    skill_hint='test-strategy + writing-plans',
)

REVIEWER = RoleConfig(
    role='reviewer',
    model_hint='medium-or-different-family-model',
    skill_hint='requesting-code-review',
)

REFINER = RoleConfig(
    role='refiner',
    model_hint='cheap-or-medium-model',
    skill_hint='code-simplifier',
)

UI_DESIGNER = RoleConfig(
    role='ui_designer',
    model_hint='strong-ui-model',
    skill_hint='ui-ux-pro-max',
)

HUMAN = RoleConfig(
    role='human',
    model_hint='n/a',
    skill_hint='manual-approval',
)
