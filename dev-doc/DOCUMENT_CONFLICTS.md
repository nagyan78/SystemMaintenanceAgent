# 文档冲突与裁决记录

> 状态：CURRENT  
> 更新日期：2026-07-11

本文件只记录已经发现并作出裁决的冲突。新增设计不得重新引入这些矛盾。

| 冲突 | 旧描述 | 当前裁决 |
|---|---|---|
| 开发路线 | 00/10/M1～M5 与 12/13～16 四阶段并存 | `ROADMAP.md` 是唯一当前路线；两套旧路线仅用于追溯 |
| Source of truth | AGENTS 要求 00、10、技术架构、旧评审均为必读 | `dev-doc/README.md` 定义优先级和最小阅读路径 |
| 当前目标 | AGENTS 声明仍处于 M1 | 已完成大量 M1～M5 骨架和主路径；当前进入 R1“可信诊断与完整结果” |
| 工作流实现 | 旧评审称 workflows.py 缺失、节点全是假数据 | 当前已有 13 节点、workflow API、service 调用和 56 个后端测试；旧评审是历史快照 |
| API 状态 | AGENTS 称 suggestions/versions 等全部 501 | suggestions、reviews、versions、workflows、reports 已有实现；taxonomy、diagnosis、chat 仍有占位 |
| Checkpointer | 旧资料称只有 MemorySaver | workflow API 已使用 SQLite checkpointer；graph 仍保留 memory helper 供测试/局部调用 |
| 前端状态 | 旧资料称只有上传和概览骨架 | 已有 workflow/review/versions/report/tree/diagnosis 等路由和页面，但完整性不等于完成 |
| Agent 可视化 | 旧文档要求展示 Thought-Action-Observation | 只展示决策摘要、工具、证据、置信度和成本；不展示原始 chain-of-thought |
| 报告归属 | 按 current_version_id 查询问题和建议 | 报告应按 workflow/run 聚合输入版本、输出版本及全部证据 |
| “完成”口径 | 有节点、API 或单测即可认为里程碑完成 | 采用 `CURRENT_IMPLEMENTATION.md` 的六项完成定义 |
| 本地命令 | `.venv/bin/python` 和 macOS 项目路径 | 当前 Windows 路径，使用 `.\.venv\Scripts\python.exe` |
| 测试基线 | 17 tests passed | 2026-07-11 实测为 56 passed、1 warning |

## 历史文档使用规则

- 旧文档中的接口、schema 和算法可作为参考；
- 出现“当前”“必须先做”“最终”“唯一”等词时，不自动获得更高优先级；
- 引用历史方案前，必须先与代码和 `CURRENT_IMPLEMENTATION.md` 核对；
- 如果历史设计仍有价值，应将相关决定提炼进当前文档，不应要求读者自己拼接多份文档。

