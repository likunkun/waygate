from __future__ import annotations

from pathlib import Path
from typing import Any


def render_scope_prompt(state: dict[str, Any], *, output_path: Path) -> str:
    return f"""生成 Requirements Scope checkpoint，并写入这个精确文件：
{output_path}

使用简体中文。保留命令、路径、JSON key 和代码标识符原文。
本 checkpoint 只负责聚焦需求范围，不展开后续分段的详细内容。

目标：
- 请求目标：`{state.get('requestedOutcome')}`
- 可行目标：`{state.get('feasibleOutcome')}`
- 当前单元：`{state.get('currentUnitId')}`

必须覆盖：
- 需求范围：当前版本要解决的问题、目标、非目标。
- 用户旅程：正常路径、局部返工路径、失败恢复路径和 legacy 兼容路径。
- 验收标准：稳定 AC id、verification layer、fixture/setup、可断言 expected。
- AO traceability：active must AO 的覆盖、延期、拒绝或范围外理由。
- 最小上下文：只记录后续 checkpoint 必须继承的事实、约束和 artifact 入口。
- 风险：需要人工 review 的假设、版本边界和迁移风险。

输出必须是 Markdown checkpoint 正文，不要写 Human Confirmation 段落。
"""


def render_product_design_prompt(state: dict[str, Any], *, output_path: Path) -> str:
    return _render_downstream_prompt(
        state,
        output_path=output_path,
        title='Product Design Brief',
        stage_goal='说明分段 Requirements package 的操作者体验、checkpoint 进度模型、artifact 审阅体验和局部返工体验。',
        upstream_stages=['scope'],
    )


def render_architecture_prompt(state: dict[str, Any], *, output_path: Path) -> str:
    return _render_downstream_prompt(
        state,
        output_path=output_path,
        title='Technical Architecture Brief',
        stage_goal='说明模块边界、数据流、state 字段、runner 合同、controller orchestration 和事件记录。',
        upstream_stages=['scope', 'product_design'],
    )


def render_test_strategy_prompt(state: dict[str, Any], *, output_path: Path) -> str:
    return _render_downstream_prompt(
        state,
        output_path=output_path,
        title='Requirements Test Strategy Brief',
        stage_goal='说明 AC 到测试用例的映射、验证层级、fixture/setup、mock policy 和回归命令。',
        upstream_stages=['scope', 'product_design', 'architecture'],
    )


def _render_downstream_prompt(
    state: dict[str, Any],
    *,
    output_path: Path,
    title: str,
    stage_goal: str,
    upstream_stages: list[str],
) -> str:
    return f"""生成 {title} checkpoint，并写入这个精确文件：
{output_path}

使用简体中文。保留命令、路径、JSON key 和代码标识符原文。

本 checkpoint 目标：
{stage_goal}

必须读取并继承以下上游 artifact path/hash/status：
{_render_upstream_artifacts(state, upstream_stages)}

要求：
- 不要依赖聊天上下文猜测上游事实；以上游 artifact path/hash 为事实入口。
- 若发现上游事实不足，写入明确风险和需要回到哪个 stage 返工。
- 输出必须是 Markdown checkpoint 正文，不要写 Human Confirmation 段落。
"""


def _render_upstream_artifacts(state: dict[str, Any], stages: list[str]) -> str:
    package = state.get('requirementsPackage')
    artifacts = package.get('artifacts') if isinstance(package, dict) else {}
    if not isinstance(artifacts, dict):
        artifacts = {}

    lines = []
    for stage in stages:
        record = artifacts.get(stage)
        if isinstance(record, dict):
            lines.append(
                f"- {stage}: path=`{record.get('path')}` hash=`{record.get('hash')}` status=`{record.get('status')}`"
            )
        else:
            lines.append(f'- {stage}: missing artifact metadata')
    return '\n'.join(lines)
