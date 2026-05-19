# Waygate 介绍与最佳实践

[English](waygate-introduction-and-best-practices.md) | [README](../../README.zh-CN.md)

本文是 V0.6.0e 用于给新同学介绍 Waygate 的材料。它只提供 Markdown source material；本版本不生成 `.pptx` 文件。

## Waygate 解决的问题

AI 编程 agent 可以很快产出有用代码，但长聊天式交付容易在流程边界失败：Requirements 漂移、Unit Plan 跳过困难验收路径、测试只证明静态检查、最终回复用自然语言声称完成却没有可审计证据。

Waygate 在 AI 编程外层加了一条 controller loop，把决策和执行分开：人确认需求和最终验收，agent 起草和实现，Verifier evidence 记录真实执行过的命令和结果。

## 角色与 Gate

- Requirements：经过审阅的范围、验收标准、journey、基础设施事实和非目标契约。
- Unit Plan：把每条验收标准映射到 test cases、commands、evidence 和当前 unit 的执行计划。
- Builder：只实现已批准当前 unit 的角色。
- Refiner：CodeSimplifier 角色，在不改变 scope 的前提下提升清晰度和可维护性。
- Reviewer：检查 defect、behavioral regression 和 missing tests 的评审角色。
- Verifier：执行计划命令并记录 structured results 的证据角色。
- Final Acceptance：面向人工 closure 的 gate，用于审阅 evidence、scope 和 rework routing。

## 事实源边界

Waygate 的价值来自把文件作为事实源，而不是依赖聊天记忆：

- `session.json` 是 controller state source。
- `events.jsonl` 是 event history。
- `approvals/` 保存人工 gate confirmation files。
- `artifacts/` 保存 prompts、runs、Verifier output、Reviewer output、Refiner output 和相关 evidence。

`README.md`、`task_plan.md`、`progress.md`、`findings.md` 等人类可读文件帮助协作理解项目，但 controller closure 依赖 approved gates 和 verifier evidence。

## 推荐使用流程

1. 从清晰 target 或 Waygate Markdown spec 启动。
2. 实现前审阅 Requirements，确认 scope、acceptance criteria、journeys、infrastructure facts 和 non-goals。
3. Builder 运行前审阅 Unit Plan，确认 test cases 映射到 AC、AO、journeys、commands 和 evidence。
4. 让 Builder 只在当前 unit 内工作。
5. 把 Refiner 和 Reviewer feedback 当作实现质量检查，而不是 approval 替代品。
6. 运行 Verifier commands 并检查 evidence rows。
7. 在 Final Acceptance 中接受、拒绝，或把 defect 路由回正确上游 gate。

对于 UI/UX 或 Web target，Requirements review 必须包含 prototype evidence、clickable webpage prototype access、page states、core click paths、real implementation targets 和 AC mapping。当前 V0.6.0e 单元是 CLI/Markdown 工作，不创建业务 UI prototype。

## 常见误用

- 把 agent 的自然语言 summary 当成证明。应使用 verifier evidence。
- 因为后续 backlog 离得近，就把当前 unit 扩展过去。V0.6.1 和 V0.6.2 必须保持 future scope，除非被明确批准。
- 用 static checks 替代 behavior tests。静态检查有价值，但不能证明 user journeys。
- 在 implementation 阶段直接修改 approved Requirements。应创建 change request 并回到正确 gate。
- 假设安装的工具就是当前 shell 实际执行的工具。应运行 `waygate doctor` 并检查 PATH shadow warning。

## 最佳实践

- 每个 target 保持足够小，确保 acceptance criteria 可审阅、可验证。
- 用明确命令替代模糊证据描述。
- 不把 secrets 写入 prompts、logs、docs 或 artifacts。
- runner 失败排查前先运行 `waygate doctor`。
- Claude Code、Codex、Plannotator 和 agent skills 默认保持 optional runtime dependencies，除非已批准 unit 明确要求。
- Debian build 应携带 docs，让安装用户和源码用户看到同样的 operations/product guidance。

## 10-12 页 PPT 大纲

这是未来讲解 deck 的大纲。V0.6.0e 不生成 PPT 或 `.pptx` 交付物。

1. 标题：Waygate 是 AI coding delivery 的 workflow control surface。
2. 问题：为什么长 AI coding chat 会丢 scope、evidence 和 state。
3. 核心思路：gates、units、evidence 和 human approval。
4. Requirements gate：scope、ACs、journeys、infrastructure facts、non-goals。
5. Unit Plan gate：test cases、commands、layers 和 traceability。
6. Builder、Refiner、Reviewer：实现、精修和评审职责分离。
7. Verifier 与 Final Acceptance：evidence rows、scope audit 和 rejection routing。
8. 事实源：`session.json`、`events.jsonl`、`approvals/` 和 `artifacts/`。
9. 推荐环境：Python、pytest、tmux runners、Plannotator port `20000`、skills 和 Debian packaging。
10. 常见失败模式，以及 Waygate 如何降低风险。
11. 示例 walkthrough：从 `waygate go V1.0` 到 final acceptance。
12. 落地 checklist：install、doctor、docs、runner choice 和 review habits。
