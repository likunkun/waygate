# 推荐环境

[English](recommended-environment.md) | [README](../../README.zh-CN.md)

本文说明 Waygate V0.6.0e 推荐的本地运行环境。它是给工作站或类 CI 打包验证环境使用的运维说明，不是新的需求 intake 格式。

## 运行时

- 推荐 Python 版本：Python 3.11 或 Python 3.12。
- 最低兼容目标：Python 3.10。
- 标准全量验证命令：

```bash
python3 -m pytest workflow_controller/tests -q
```

建议源码运行和测试使用同一个 Python 环境。如果使用 virtualenv，请先激活环境再运行 Waygate 或 pytest，避免导入的 `workflow_controller` package 和命令行工具不一致。

## Runner 工具

Waygate 可以通过 `subprocess` runner 不依赖 tmux agent pane 执行，但常用交互流程依赖 tmux runner：

- `tmux-claude` 需要 `tmux` 和 Claude Code。Waygate 在 tmux 内启动且未指定 pane 时，可以创建 Claude Code pane。
- `tmux-codex` 需要 `tmux` 和已有 Codex pane。Waygate 可以在当前 tmux session 中发现匹配的 Codex pane。
- `waygate doctor` 会报告 `tmux` 命令是否存在，以及当前 shell 是否处于 tmux session。

Claude Code、Codex 和 Plannotator 是可选 runtime 工具，不是 Debian package 的强依赖。缺少这些可选工具时，`waygate doctor` 应输出 warning/manual action，而不是让 doctor 命令失败。

## 人工审阅

Plannotator 是可选但推荐的浏览器辅助审阅工具，可用于 Requirements、Unit Plan 和 Final Acceptance gate。推荐 Plannotator port 是 `20000`。

常用审阅配置：

```bash
waygate go V1.0 --plannotator-port 20000
```

Requirements approval 仍以 `approvals/requirements-and-acceptance.md` 为事实源。UI/Web 工作中出现的 prototype review HTML 只是辅助审阅视图，不是 approval source。

## Agent skills

Waygate 不安装 agent skills。skills 属于 Claude Code、Codex 等被选中的 agent runtime。需要某个 role 使用的 skills，应在对应 runtime 中安装。

`waygate doctor` 会扫描常见本地 skill 根目录：

- `~/.agents/skills`
- `~/.codex/skills`
- `~/.codex/superpowers/skills`
- `~/.config/opencode/skills`

它会报告可读的 `SKILL.md`，并在缺少 planning、brainstorming、TDD、systematic debugging、test strategy、code simplification、verification-before-completion 等推荐 workflow skills 时给出 warning。这些 warning 只是建议；workflow 完成依据仍然是 controller state 和 gate artifacts。

推荐边界：

- planning、TDD、debugging、testing strategy、verification、code simplification 等 workflow skills 放在 agent 环境中。
- 不要假设 Debian package 会安装或升级这些 skills。
- skills 提升 role 能力；`session.json`、`events.jsonl`、`approvals/` 和 `artifacts/` 仍是 workflow facts。

## Debian packaging

构建包需要 shell 工具和 `dpkg-deb`：

```bash
bash packaging/debian/build-deb.sh
```

生成的 package 会把 `waygate` wrapper 安装到 `/usr/bin/waygate`，Python package 安装到 `/usr/lib/waygate`，用户文档安装到 `/usr/share/doc/waygate`。

V0.6.0e 还会安装：

- `/usr/share/doc/waygate/docs/operations/recommended-environment.md`
- `/usr/share/doc/waygate/docs/operations/recommended-environment.zh-CN.md`
- `/usr/share/doc/waygate/docs/product/waygate-introduction-and-best-practices.md`
- `/usr/share/doc/waygate/docs/product/waygate-introduction-and-best-practices.zh-CN.md`

## PATH shadow 处理

如果 `~/.local/bin/waygate` 这类用户级 wrapper 排在 `/usr/bin/waygate` 前面，shell 可能运行旧 wrapper，即使 Debian package 已正确安装。这种情况称为 PATH shadow。

使用：

```bash
waygate doctor
```

如果报告显示 PATH shadow，请在确认目标安装源后手工改名或删除用户级 wrapper，然后执行：

```bash
hash -r
```

Debian post-install 只提示 PATH shadow 风险，不删除用户文件。
