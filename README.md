# 标准产品体系维护与诊断系统

## 1. 项目简介

本项目是一个面向标准产品分类体系的维护与诊断工具，用于读取 Excel / CSV 格式的标准产品分类数据，构建分类树，检查结构类、内容类和同义词类问题，并生成诊断结果、体系评分和报告。

系统以规则诊断为主体，可选接入本地 Ollama 大模型进行语义辅助分析。未配置 AI 时，系统仍可完成数据读取、树结构构建、规则检查、评分和报告生成。系统不会自动修改原始 Excel 文件，诊断结果用于人工复核、课程设计报告和答辩展示。

## 2. 项目目标

系统主要用于发现和说明以下问题：

- 层级过深、节点过宽、结构不均衡、父节点缺失和孤立节点。
- 节点重复、重复挂载、父子关系异常、父子节点同名和命名冗余。
- 同义词缺失、同义词重复、同义词异常或语义偏移。
- 缺少统一评价指标，难以量化体系健康程度。
- 版本对比能力已提供基础实现；修改日志、回滚和完整版本管理属于后续扩展方向。

## 3. 核心功能

当前代码已经实现的功能包括：

- Excel / CSV 数据读取和字段标准化。
- 从 `parent_id` 构建分类树，也可从 `category_group_id` 推导直接父节点。
- 层级深度、节点宽度、叶子节点、子树规模和路径统计。
- 结构类规则诊断，包括层级过深、分支过宽、结构不均衡、父节点缺失、孤立节点和循环关系。
- 内容类规则诊断，包括全局重名、同级重名、父子同名、疑似名称冗余和疑似父子关系异常。
- 同义词类诊断，包括同义词覆盖、重复同义词和异常同义词。
- 体系健康评分，包括结构、内容、同义词和冗余控制维度。
- Markdown / JSON 报告生成。
- 本地 Web 上传诊断页面，支持上传 `.xlsx` 并展示 HTML 诊断看板。
- 可选 Ollama 语义分析，用于辅助判断高语义依赖的问题。
- 命令行诊断入口和单元测试。
- 基础版本对比，可比较两个版本中的新增、删除、名称、父节点和同义词变化。

尚未完整实现的能力包括自动修复、完整维护日志、历史版本回滚、在线 OpenAI / Google 模型调用流程和面向生产的大规模性能优化。

## 4. 系统架构

系统采用分层结构：

- 前端展示层：`src/web_app.py` 提供本地上传页面和结果展示。
- 后端服务层：接收上传文件，临时读取 Excel，并调用诊断流程。
- 数据处理层：`src/advanced/data_loader.py` 读取 CSV / Excel，统一字段别名。
- 分类树构建层：`src/advanced/tree_builder.py` 生成父子关系、路径、深度、宽度、子树规模等派生字段。
- 规则诊断层：`src/advanced/diagnostics.py` 和 `src/advanced/rule_checker.py` 执行结构、内容和同义词规则检查。
- AI 语义分析层：`src/advanced/ollama_analyzer.py` 在启用 Ollama 时抽取候选问题进行语义判断。
- 评分与报告层：`src/advanced/evaluator.py`、`src/advanced/report_writer.py` 和 `src/report_generator.py` 生成评分、Markdown、JSON 和 HTML 看板。

典型流程：

```text
用户上传数据
→ 后端接收文件
→ 解析 Excel / CSV
→ 字段标准化
→ 构建分类树
→ 执行规则诊断
→ 可选调用 Ollama 语义分析
→ 计算体系评分
→ 生成诊断报告
→ 前端页面展示
```

## 5. 项目目录结构

```text
├── README.md                         # 项目总说明文档，介绍项目功能、运行方式、目录结构和交接说明
├── requirements.txt                  # Python 依赖列表，用于安装项目运行所需第三方库
├── .env.example                      # 环境变量配置示例，用于配置 AI 分析、本地模型或 API Key
├── .gitignore                        # Git 忽略规则，避免提交缓存、虚拟环境、输出文件等无关内容
├── main.py                           # 命令行诊断入口，用于执行完整诊断流程并生成报告
├── start_upload_frontend.bat         # Windows 一键启动脚本，用于快速打开本地上传诊断页面

├── src/                              # 项目核心源代码目录
│   ├── web_app.py                    # 本地 Web 服务入口，负责文件上传、诊断调用和结果页面展示
│   ├── report_generator.py           # 报告生成模块，负责生成 Markdown / HTML 等诊断报告
│   ├── data_loader.py                # 基础数据读取模块，负责读取 Excel / CSV 标准产品数据
│   ├── tree_builder.py               # 基础分类树构建模块，根据节点关系构建树形结构
│   ├── tree_analyzer.py              # 树结构分析模块，用于统计层级、宽度、叶子节点等结构指标
│   ├── structure_checker.py          # 结构问题检查模块，用于检测层级过深、分支过宽等问题
│   ├── common.py                     # 通用工具与公共数据结构，存放项目共用函数或对象定义
│   └── advanced/                     # 高级诊断模块目录，包含完整规则诊断、评分、AI 分析和报告输出逻辑
│       ├── main.py                   # 高级诊断入口，组织完整诊断流程
│       ├── data_loader.py            # 高级数据读取模块，负责字段兼容、数据清洗和标准化处理
│       ├── tree_builder.py           # 高级树构建模块，负责构建更完整的分类树和节点映射关系
│       ├── diagnostics.py            # 诊断流程调度模块，汇总结构、内容、同义词等问题检查结果
│       ├── rule_checker.py           # 规则检查模块，基于规则识别明确的问题节点
│       ├── evaluator.py              # 体系评价模块，用于计算结构、内容、同义词等维度评分
│       ├── metrics.py                # 指标计算模块，负责树深度、节点宽度、覆盖率等统计指标计算
│       ├── report_writer.py          # 报告写入模块，负责输出 Markdown / JSON / HTML 等结果文件
│       ├── ollama_analyzer.py        # 本地 Ollama 模型分析模块，用于调用本地大模型进行语义判断
│       ├── llm_judge.py              # 大模型判断封装模块，负责组织 AI 判断流程和解析模型结果
│       ├── prompts.py                # Prompt 模板模块，存放 AI 分析所需提示词模板
│       ├── version_compare.py        # 版本对比模块，用于后续支持不同版本体系的差异分析
│       └── config.py                 # 配置模块，存放规则阈值、模型配置和系统参数

├── docs/                             # 项目文档目录，存放设计说明、问题分析、流程说明和整理报告
│   ├── 解决方案.md                   # 系统解决方案说明，包含算法设计、AI 分析策略和优化思路
│   ├── 工作流程问题.md               # 当前流程和页面展示中存在的问题，以及后续修改建议
│   ├── 工作流程图.md                 # 系统工作流程图和 Agent 流程说明
│   ├── 项目整理报告.md               # 项目文件整理说明，记录目录调整、文件移动和交接整理情况
│   └── 分析/                         # 前期分析文档目录，存放需求、数据、计划和问题梳理材料
│       ├── 会议总结.md               # 课程任务说明和项目目标来源，记录老师要求和分组安排
│       ├── 数据结构概况.md           # 标准产品体系数据结构说明，解释字段含义、树结构和统计特征
│       ├── 日程.md                   # 项目周计划和每日任务安排
│       └── 问题分析.md               # 标准产品体系存在的问题分类，包括结构、内容、评价和版本问题

├── data/                             # 数据目录，存放原始数据、处理后数据和样例数据
│   ├── raw/                          # 原始数据目录，用于存放未经处理的标准产品体系数据
│   ├── processed/                    # 处理后数据目录，用于存放清洗、转换或中间处理结果
│   └── sample/                       # 样例数据目录，用于测试系统运行和演示诊断流程
│       ├── temp_company_product_0522_1.xlsx    # 样例 Excel 数据文件
│       └── 产品标准体系.xlsx                   # 标准产品体系样例数据文件

├── outputs/                          # 输出结果目录，存放系统运行后生成的报告、图表和问题清单
│   ├── reports/                      # 诊断报告输出目录，存放 Markdown / HTML / JSON 报告
│   ├── charts/                       # 图表输出目录，存放统计图、评分图等可视化结果
│   ├── issues/                       # 问题清单输出目录，存放结构问题、内容问题、AI 分析结果等明细
│   └── screenshots/                  # 页面截图目录，用于保存前端页面或答辩展示截图

├── assets/                           # 静态资源目录，存放图片、流程图、展示素材等
│   └── images/                       # 图片资源目录，用于存放系统架构图、流程图、页面截图等图片文件

└── tests/                            # 测试代码目录，用于存放单元测试或功能测试脚本
```

主要文件说明：

- `main.py`：高级命令行诊断入口，内部调用 `src.advanced.main`。
- `src/web_app.py`：本地上传诊断页面。
- `src/report_generator.py`：HTML 看板和首轮 Markdown 报告生成。
- `src/advanced/data_loader.py`：高级诊断的数据读取和字段兼容。
- `src/advanced/diagnostics.py`：Web 诊断使用的规则诊断集合。
- `src/advanced/report_writer.py`：命令行 Markdown / JSON 报告输出。
- `docs/`：项目背景、数据结构、问题分析、算法设计和流程说明。
- `data/sample/`：课程设计样例数据。
- `outputs/reports/`：诊断输出结果。
- `tests/`：单元测试。

## 6. 环境要求

- Python 3.10 或更高版本。
- Windows / macOS / Linux。
- 依赖库见 `requirements.txt`。
- Web 上传页面推荐在本机浏览器中使用。
- 如需启用 AI 语义分析，需要安装并启动 Ollama，并准备本地模型，例如 `qwen3:8b`。

## 7. 安装步骤

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 8. 配置说明

复制 `.env.example` 为 `.env` 后按需修改。AI 语义分析是可选增强功能，不配置时仍可运行规则诊断。

当前自动 AI 分析流程实际使用 Ollama：

```env
ENABLE_AI_ANALYSIS=true
MODEL_PROVIDER=ollama
MODEL_NAME=qwen3:8b
OLLAMA_BASE_URL=http://localhost:11434
AI_MAX_ITEMS=1
```

命令行规则阈值：

```env
MAX_DEPTH=8
MAX_CHILDREN=2000
```

代码中的配置对象可以读取 `OPENAI_API_KEY` 和 `GOOGLE_API_KEY`，但当前自动分析流程没有实现在线 OpenAI / Google 调用，不应将其写成已支持的完整功能。

## 9. 运行方式

### 9.0 启动 FastAPI 后端骨架

当前仓库已新增 `backend/` 后端骨架，可先启动本地 API 网关：

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

可访问：

- `GET http://127.0.0.1:8000/api/health`
- `POST http://127.0.0.1:8000/api/files/upload`
- `GET http://127.0.0.1:8000/docs`

### 9.1 启动本地上传诊断页面

Windows 可以双击：

```text
start_upload_frontend.bat
```

也可以命令行启动：

```powershell
python -m src.web_app --host 127.0.0.1 --port 8765 --open-browser
```

浏览器打开后上传 `.xlsx` 文件即可生成诊断看板。上传文件只会被本地临时读取，不会写回或修改原始 Excel。

### 9.2 命令行诊断

```powershell
python main.py --input data/sample/产品标准体系.xlsx --output outputs/reports/report.md
```

自定义阈值：

```powershell
python main.py --input data/sample/产品标准体系.xlsx --output outputs/reports/report.md --max-depth 8 --max-children 2000
```

版本对比：

```powershell
python main.py --input data/sample/产品标准体系.xlsx --compare data/sample/temp_company_product_0522_1.xlsx --output outputs/reports/version_compare_report.md
```

### 9.3 运行测试

```powershell
python -m pytest
```

## 10. 数据格式说明

标准产品体系数据通常包含以下字段：

| 字段名 | 说明 |
| --- | --- |
| `category_id` | 当前节点 ID |
| `category_name` | 当前节点名称 |
| `category_group_id` | 祖先节点 ID 路径，可用于推导父节点 |
| `category_pids` | 父节点路径，可能包含虚拟根节点 |
| `category_group_name` | 祖先节点名称路径 |
| `syn_list` | 同义词列表 |

`category_group_id` 不是单个父节点，而是一条从顶层节点到当前节点父节点的祖先路径。当前节点的直接父节点通常是 `category_group_id` 中最后一个 ID；如果该字段为空，节点可能是顶层节点。

高级数据读取模块还兼容以下字段别名：

| 标准字段 | 兼容字段 |
| --- | --- |
| `category_id` | `id`、`node_id`、`cat_id` |
| `category_name` | `name`、`node_name`、`cat_name` |
| `parent_id` | `parent`、`pid`、`parent_category_id` |
| `synonyms` | `syn_list`、`synonym`、`alias`、`aliases` |

因此系统主要支持路径式分类数据，也兼容直接提供 `parent_id` 的树形数据。具体字段以当前代码实际读取逻辑为准。

## 11. 使用流程

1. 阅读本 README，了解项目目标和运行方式。
2. 根据 `requirements.txt` 安装依赖。
3. 启动本地 Web 页面或运行命令行入口。
4. 使用 `data/sample/` 中的样例 Excel 验证系统。
5. 上传或传入真实标准产品体系 Excel。
6. 查看诊断概览、问题统计、问题明细和评分结果。
7. 如需 AI 辅助分析，先配置 `.env` 并启动 Ollama。
8. 根据报告中的判断依据和建议进行人工复核。

## 12. 诊断方法说明

结构类问题主要依靠规则统计：

- 层级过深：基于树深度、叶子深度均值和标准差等指标判断。
- 节点过宽：基于直接子节点数量和相对分支宽度判断。
- 结构不均衡：基于子树规模差异、最大/最小规模比和信息熵判断。
- 父节点缺失和孤立节点：检查父节点引用是否存在，以及节点是否能从根节点访问。
- 叶子节点占比异常：判断某些分支是否可能还需要继续细分。

内容类问题结合规则和可选语义分析：

- 节点重复：检查全局同名和同父节点下同名。
- 父子同名：检查父节点与子节点名称是否完全相同。
- 疑似名称冗余：检查父子名称是否存在高度包含关系。
- 疑似父子关系异常：筛选缺少明显词面关联的父子组合，交由 AI 或人工复核。

同义词类问题包括：

- 同义词覆盖率统计。
- 无同义词节点统计。
- 同义词重复。
- 同义词与标准名称完全相同。
- 同义词长度异常。

部分文档中提到的自动修复、全量语义纠错、完整修改追踪和回滚属于设计思路或后续优化，不属于当前已完整实现能力。

## 13. AI 辅助分析说明

AI 在系统中是规则诊断的补充，不替代规则和人工确认。

当前自动 AI 分析流程位于 `src/advanced/ollama_analyzer.py`，只在满足以下条件时运行：

- `ENABLE_AI_ANALYSIS=true`。
- `MODEL_PROVIDER=ollama`。
- `MODEL_NAME` 已配置。
- 已安装 `langchain-ollama`。
- 本地 Ollama 服务可访问。

AI 会从规则命中的候选问题中抽取样本，构造包含父节点、当前节点、子节点、兄弟节点和路径信息的 Prompt，要求模型输出 JSON 格式判断结果，包括是否确认问题、置信度、语义关系、原因和修改建议。AI 结果只作为辅助参考，最终仍需人工复核。

## 14. 输出结果说明

系统可能输出以下内容：

- 数据概况：总节点数、根节点数、最大深度、最大直接子节点数、叶子节点占比等。
- 问题概览：问题总数、风险分布、主要问题类型。
- 问题明细：节点 ID、节点名称、路径、问题类型、判断依据、建议和人工确认标记。
- AI 分析结果：是否确认问题、置信度、语义原因和修改建议。
- 健康评分：结构健康分、内容质量分、同义词完整度分、冗余控制分和综合健康分。
- Markdown 报告。
- JSON 报告。
- Web 页面中的 HTML 诊断看板。

## 15. docs 文档阅读顺序

建议按以下顺序阅读：

1. `docs/分析/会议总结.md`：课程任务背景和总体要求。
2. `docs/分析/数据结构概况.md`：标准产品体系 Excel 字段、树结构和数据统计。
3. `docs/分析/问题分析.md`：结构、内容、评价和版本问题定义。
4. `docs/解决方案.md`：算法设计、阈值思路和 AI 语义分析设计。
5. `docs/工作流程图.md`：流程图占位说明，图片需人工补充。
6. `docs/工作流程问题.md`：当前展示和诊断结果中的待优化点。
7. `docs/分析/日程.md`：课程设计阶段安排。
8. `docs/项目整理报告.md`：本次文件夹整理、移动和修改记录。

## 16. 当前不足与后续优化

- Web 页面展示还可继续优化，特别是大表格字段展示和问题类型排序。
- 部分统计值应作为背景信息展示，不应全部作为诊断问题。
- `balance_ratio`、`entropy` 等指标需要继续转化为更易理解的中文解释。
- AI 输出需要进一步稳定格式，并增加置信度和依赖程度说明。
- 规则阈值需要结合更多真实数据调参。
- 大规模数据下的性能仍可优化。
- 当前有基础版本对比，但修改日志、维护审计、历史回滚尚未完整实现。
- 在线 OpenAI / Google API 调用尚未接入自动诊断流程。
- `docs/工作流程图.md` 中原本引用的本机图片缺失，需要补充到 `assets/images/`。

## 17. 项目交接说明

接手项目时建议：

1. 先阅读本 README。
2. 再阅读 `docs/分析/数据结构概况.md` 和 `docs/解决方案.md`。
3. 按安装步骤创建虚拟环境并安装依赖。
4. 使用 `data/sample/产品标准体系.xlsx` 运行一次 Web 上传诊断或命令行诊断。
5. 查看 `outputs/reports/` 中的 Markdown / JSON 报告。
6. 如需启用 AI，先安装 Ollama、拉取模型并配置 `.env`。
7. 后续开发优先查看 `src/web_app.py`、`src/advanced/data_loader.py`、`src/advanced/tree_builder.py`、`src/advanced/diagnostics.py`、`src/advanced/report_writer.py` 和 `tests/`。
