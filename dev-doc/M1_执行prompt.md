# M1 里程碑执行 Prompt

> 用途：把以下 prompt 整体复制给 AI 编程助手（Cursor / Claude Code / 工程师 agent），启动 M1 里程碑的代码实现。
> 项目路径：/Users/flflfl/Documents/code/SystemMaintenanceAgent

---

## 复制以下内容作为 Prompt

```
你是一个资深 Python 后端工程师，现在要在现有项目上实现 M1 里程碑：工作流骨架接真实数据（确定性闭环）。

## 项目背景
项目名：产品标准体系维护智能体（FastAPI + LangGraph + SQLite）。
当前状态：FastAPI 骨架 + SQLite 7 表 + Excel 上传已可用；LangGraph 12 节点拓扑已搭好但全部硬编码假数据。M1 的目标是把硬编码替换为真实 service 调用，跑通"上传→解析→建树→保存版本→结构诊断→报告"的确定性闭环。

## 必读文档（开工前先读，不要跳过）
1. dev-doc/00_开发里程碑索引.md — 读 §4 M1 章节（文件清单/数据结构/接口契约/实现顺序/验收标准/禁止行为）
2. dev-doc/01_Excel上传与导入开发设计.md — Excel 解析字段定义
3. dev-doc/02_分类树解析与体系概览开发设计.md — 树构建算法（父子关系/level/path 推导）
4. dev-doc/03_结构诊断开发设计.md — 结构诊断规则（父节点缺失/层级过深>7/节点过宽>80/重复名称）
5. dev-doc/08_导出与诊断报告开发设计.md — 报告模板（M1 阶段模板化，不调 LLM）
6. dev-doc/10_LangGraph智能体工作流开发设计.md — §5 State 定义、§8 节点设计、§10 graph 构建

## M1 涉及节点（只实现这 5 个，其余节点保留占位返回空结果）
| 节点 | 调用的 service |
|------|---------------|
| parse_excel_node | excel_service.parse_uploaded_file(file_id) |
| build_tree_node | taxonomy_service.build_tree(file_id) |
| save_initial_version_node | version_service.create_initial_version(file_id) |
| structure_diagnosis_node | diagnosis_service.run_structure_diagnosis(version_id) |
| generate_report_node | report_service.generate_diagnosis_report(version_id) |

## 文件清单（新建/修改）
新建：
- backend/app/api/workflows.py（workflow 启动/状态 API）
- backend/app/services/taxonomy_service.py（树构建 + 概览）
- backend/app/services/diagnosis_service.py（结构诊断纯规则）
- backend/app/services/version_service.py（版本创建/查询）
- backend/app/services/report_service.py（模板化报告）
- backend/app/repositories/taxonomy_repo.py（节点 CRUD）
- backend/app/repositories/diagnosis_repo.py（问题记录 CRUD）
- backend/app/repositories/version_repo.py（版本 CRUD）
- backend/app/repositories/task_repo.py（task_record + workflow_event）
- backend/app/schemas/taxonomy.py、issue.py、version.py

修改：
- backend/app/services/excel_service.py（补全 parse 逻辑）
- backend/app/db.py（扩展 task_record + 新建 workflow_event 表）
- backend/app/agents/nodes.py（替换 5 个节点的硬编码为 service 调用）
- backend/app/agents/graph.py（保留拓扑，节点接真实 service）
- backend/app/main.py（注册 workflows 路由）

## 数据结构

### task_record 表扩展
ALTER TABLE task_record ADD COLUMN workflow_id TEXT;
ALTER TABLE task_record ADD COLUMN thread_id TEXT;
ALTER TABLE task_record ADD COLUMN version_id INTEGER;
ALTER TABLE task_record ADD COLUMN progress INTEGER DEFAULT 0;
ALTER TABLE task_record ADD COLUMN interrupt_payload TEXT;
ALTER TABLE task_record ADD COLUMN result_payload TEXT;

### workflow_event 表（新建）
CREATE TABLE workflow_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    task_id TEXT,
    node_name TEXT,
    event_type TEXT NOT NULL,
    status TEXT,
    progress INTEGER,
    message TEXT,
    payload TEXT,
    created_time DATETIME DEFAULT CURRENT_TIMESTAMP
);

## 接口契约

### API 1：启动工作流
POST /api/workflows/taxonomy/start
请求：{ "file_id": 1 }
响应：{ "task_id": "...", "workflow_id": "...", "thread_id": "...", "status": "running", "current_step": "parse_excel", "progress": 0 }

### API 2：查询工作流状态
GET /api/workflows/{task_id}
响应：{ "task_id": "...", "status": "completed", "current_step": "completed", "progress": 100, "file_id": 1, "current_version_id": 1, "version_no": "v1.0", "node_count": 21090, "structure_issue_count": 128, "report_path": "/data/reports/v1.0_diagnosis_report.md" }

### Service 函数签名
def parse_uploaded_file(file_id: int) -> ParseExcelResult
def build_tree(file_id: int) -> BuildTreeResult
def get_overview(version_id: int) -> OverviewResult
def create_initial_version(file_id: int) -> CreateVersionResult
def run_structure_diagnosis(version_id: int, max_depth: int = 7, max_children: int = 80) -> StructureDiagnosisResult
def generate_diagnosis_report(version_id: int) -> ReportResult

## 实现顺序（严格按此顺序，有依赖关系）
1. 扩展 task_record 表 + 新建 workflow_event 表（改 db.py）
2. 实现 repositories/task_repo.py（task_record CRUD + workflow_event 写入）
3. 补全 services/excel_service.py（已有骨架，补全 parse 逻辑）
4. 新建 services/taxonomy_service.py（build_tree + get_overview）
5. 新建 repositories/taxonomy_repo.py（节点批量写入 + 查询）
6. 新建 services/version_service.py（create_initial_version）
7. 新建 repositories/version_repo.py（版本 CRUD）
8. 新建 services/diagnosis_service.py（run_structure_diagnosis，纯规则）
9. 新建 repositories/diagnosis_repo.py（问题记录批量写入）
10. 新建 services/report_service.py（模板化 Markdown 报告）
11. 新建 api/workflows.py（start + status 两个 API）
12. 修改 agents/nodes.py（替换 5 个节点硬编码为 service 调用）
13. 修改 agents/graph.py（保留拓扑，节点接真实 service）
14. 编写 M1 集成测试（上传→start→status→验证真实数据）

## 验收标准（全部要满足）
1. 上传样例 Excel 后，调 POST /api/workflows/taxonomy/start，返回 task_id
2. 调 GET /api/workflows/{task_id} 能看到真实进度（非硬编码 progress 值）
3. 结构诊断检测到 44 个父节点缺失（来自真实数据，非硬编码 44）
4. 生成 v1.0 版本记录，node_count = 21090
5. 生成 Markdown 报告（模板化，非 LLM 生成），包含真实统计数据
6. task_record 表有 workflow_id/thread_id/progress 字段
7. workflow_event 表有节点流转记录

## 禁止行为（硬约束，违反即返工）
- 禁止在 node 函数中写业务逻辑（树构建算法、诊断规则等），必须调 service
- 禁止在 M1 阶段调用 LLM 或 Qdrant
- 禁止硬编码 structure_issue_count = 44 等固定值
- 禁止跳过 save_initial_version_node 直接做诊断
- 禁止在 report_node 中调 LLM（M1 阶段报告是模板化）
- 禁止 node 函数超过 30 行（超出说明把业务逻辑写进了 node）

## 完成后
1. 运行 pytest 确保全部测试通过
2. 启动服务，用样例 Excel 实际跑一遍 workflow，验证 7 条验收标准
3. 输出代码摘要：列出新建/修改的文件和每个文件的核心函数
```
