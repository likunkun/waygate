from __future__ import annotations

from pathlib import Path
from typing import Any


DOC_DIRECTORIES = (
    Path('docs/product'),
    Path('docs/architecture'),
    Path('docs/workflow'),
    Path('docs/operations'),
)


def ensure_agent_operating_guides(
    workspace_dir: Path,
    *,
    enabled: bool = True,
    include_claude: bool = False,
) -> dict[str, Any]:
    workspace_dir = workspace_dir.resolve()
    if not enabled:
        return {
            'workspacePath': str(workspace_dir),
            'enabled': False,
            'agents': {'status': 'skipped'},
            'claude': {'status': 'skipped'},
            'docDirectories': [],
        }

    workspace_dir.mkdir(parents=True, exist_ok=True)
    doc_dirs = _ensure_doc_directories(workspace_dir)
    agents = _write_or_draft(
        workspace_dir / 'AGENTS.md',
        _agents_md_template(),
    )
    claude = (
        _write_or_draft(workspace_dir / 'CLAUDE.md', _claude_md_template())
        if include_claude
        else {'status': 'skipped'}
    )
    return {
        'workspacePath': str(workspace_dir),
        'enabled': True,
        'agents': agents,
        'claude': claude,
        'docDirectories': [str(path) for path in doc_dirs],
    }


def _ensure_doc_directories(workspace_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for relative_path in DOC_DIRECTORIES:
        path = workspace_dir / relative_path
        path.mkdir(parents=True, exist_ok=True)
        paths.append(path)
    return paths


def _write_or_draft(path: Path, content: str) -> dict[str, str]:
    if path.exists():
        existing = path.read_text(encoding='utf-8')
        if existing == content:
            return {'status': 'unchanged', 'path': str(path)}
        draft_path = path.with_name(path.name + '.generated')
        draft_path.write_text(content, encoding='utf-8')
        return {
            'status': 'drafted',
            'path': str(path),
            'draftPath': str(draft_path),
        }

    path.write_text(content, encoding='utf-8')
    return {'status': 'created', 'path': str(path)}


def _agents_md_template() -> str:
    return """# AGENTS.md

这是本项目的 Agent 操作规范，也是所有 agent 入口文件中的唯一权威规则源。

## 必读文件

开始行动前，先读取以下文件；文件不存在时跳过，但不要凭聊天上下文替代事实源：

1. `AGENTS.md`
2. `ROADMAP.md`
3. `task_plan.md`
4. `progress.md`
5. `findings.md`
6. Controller state-dir 中的 `session.json`（如 `.rrc-controller-<target>/session.json`）

## 事实源

| 信息 | 权威来源 | 说明 |
|---|---|---|
| 版本规划 | `ROADMAP.md` | 不要只根据最近进度推断版本范围。 |
| 当前开发计划 | `task_plan.md` | 长任务计划、阶段状态和完成记录。 |
| 当前控制器状态 | `<state-dir>/session.json` | 存在时，它是 workflow state 的事实源。 |
| 事件历史 | `<state-dir>/events.jsonl` | gate、runner 和状态转移事件。 |
| 人工确认 | `<state-dir>/approvals/` | Requirements、Unit Plan 和 Final Acceptance gate。 |
| 验收证据 | `<state-dir>/artifacts/` | Verifier、Reviewer、Refiner 和 AO 相关 artifact。 |
| 人类可读进度 | `progress.md` | 只能作为摘要，不能单独作为完成依据。 |
| 决策与已知问题 | `findings.md` | 历史决策、根因、约束和风险。 |

## 文档目录

项目文档使用以下目录结构：

```text
docs/
  product/
  architecture/
  workflow/
  operations/
```

目录含义：

- `docs/product/`：产品背景、用户旅程、需求说明。
- `docs/architecture/`：技术架构、模块边界、关键设计决策。
- `docs/workflow/`：开发流程、agent 流程、验收流程。
- `docs/operations/`：运行、部署、排障和运维说明。

## 工程行为准则

- 写代码前先想清楚：明确假设、指出不确定点，需求模糊时先澄清。
- 优先选择满足当前 unit 的最简单实现，避免过度设计。
- 精准修改：每一处改动都应能追溯到当前 unit、缺陷修复或验证需要。
- 不做无关重构、无关格式化、无关删除，除非当前任务明确要求。
- 把模糊任务转成可验证的完成条件，再进入实现。
- 修 bug 时先说明失败条件或复现路径，再用证据验证修复结果。

## 工作流规则

- 一次只处理一个 unit。
- 不要把自然语言总结当作完成依据。
- 完成必须依赖 verifier evidence 和 controller state transition。
- 不要绕过 Requirements、Unit Plan、Verifier 或 Final Acceptance gate。
- 实现阶段不要修改已批准的 requirements 或 acceptance criteria。
- 如果需求必须变更，先创建 change request，再回到对应 gate。
- 除非 controller 明确路由，否则实现改动必须限制在当前 unit 内。

## 验证

使用 `task_plan.md` 或 `progress.md` 中记录的项目验证命令。
对本 controller 项目，标准全量验证命令是：

```bash
source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q
```

## 安全规则

- 不要回滚无关的用户改动。
- 不要添加未跟踪的历史 controller 目录，除非用户明确要求。
- 不要在 artifact 或日志里暴露环境变量值、token、数据库 URL 或其他秘密。
- 保留已有生成物；只有当前任务明确拥有它们时才修改。
"""


def _claude_md_template() -> str:
    return """# CLAUDE.md

本项目使用 `AGENTS.md` 作为唯一权威 Agent 操作规范。

开始行动前，先读取：

1. `AGENTS.md`
2. `ROADMAP.md`
3. `task_plan.md`
4. `progress.md`
5. `findings.md`
6. Controller state-dir 中的 `session.json`，如果存在
"""
