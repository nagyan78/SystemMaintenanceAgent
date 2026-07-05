# 标准产品体系维护智能体

这是一个面向“产品标准分类体系维护”的本地智能体平台骨架。当前版本重点完成了 FastAPI 后端基础工程：本地启动、健康检查、Excel 上传、SQLite 初始化，以及后续分类树、诊断、建议、版本、问答等模块的 API 边界。

当前代码还不是完整诊断系统，`taxonomy`、`diagnosis`、`suggestions`、`versions`、`chat` 等业务接口已预留路由，但会返回 `501 Not Implemented`，等待后续功能接入。

## 环境要求

- Python 3.10 或更高版本
- macOS / Linux / Windows 均可
- 不需要单独安装 SQLite；项目使用 Python 标准库 `sqlite3`

## 安装依赖

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

## 启动后端

macOS / Linux：

```bash
.venv/bin/python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

启动后访问：

- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/health

健康检查正常返回示例：

```json
{
  "status": "ok",
  "app": "standard-taxonomy-agent"
}
```

## 上传样例 Excel

启动后端后，可以用样例文件测试上传接口。

macOS / Linux：

```bash
curl -F "file=@data/sample/产品标准体系.xlsx" \
  http://127.0.0.1:8000/api/files/upload
```

成功返回示例：

```json
{
  "file_id": 1,
  "task_id": "import_excel_xxxxxxxxxxxx",
  "file_name": "产品标准体系.xlsx",
  "row_count": 21090,
  "column_count": 6,
  "columns": [
    "category_id",
    "category_name",
    "category_group_id",
    "category_pids",
    "category_group_name",
    "syn_list"
  ],
  "status": "uploaded"
}
```

上传后会自动生成本地运行数据：

```text
data/app.db
data/uploads/
```

这些文件和目录已在 `.gitignore` 中忽略。

## 当前可用接口

| 方法 | 路径 | 状态 |
| --- | --- | --- |
| GET | `/api/health` | 可用 |
| POST | `/api/files/upload` | 可用 |
| GET | `/api/files` | 可用 |
| GET | `/api/files/{file_id}` | 可用 |
| GET | `/api/taxonomy/overview` | 占位，返回 501 |
| POST | `/api/diagnosis/run` | 占位，返回 501 |
| GET | `/api/suggestions` | 占位，返回 501 |
| GET | `/api/versions` | 占位，返回 501 |
| POST | `/api/chat` | 占位，返回 501 |

## 运行测试

macOS / Linux：

```bash
.venv/bin/python -m pytest -q
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python -m pytest -q
```

当前测试覆盖：

- FastAPI 健康检查
- SQLite 表结构初始化
- Excel 上传、字段识别、文件记录写入
- 后续业务模块 API 占位边界
- LangGraph 状态模型默认值

## 项目结构

```text
.
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI 应用入口
│   │   ├── config.py               # 本地配置
│   │   ├── db.py                   # SQLite 初始化和连接
│   │   ├── api/                    # API 路由
│   │   ├── agents/                 # LangGraph 工作流骨架
│   │   ├── repositories/           # SQLite 数据访问
│   │   ├── schemas/                # Pydantic 响应模型
│   │   ├── services/               # 业务服务
│   │   ├── tools/                  # 分类树、校验、导出工具占位
│   │   └── vectorstores/           # Qdrant 适配器占位
│   └── tests/                      # 后端测试
├── data/
│   └── sample/                     # 样例 Excel
├── dev-doc/                        # PRD 和技术设计文档
├── docs/
│   └── superpowers/plans/          # 实施计划
├── requirements.txt
└── README.md
```

## 数据库说明

项目启动时会自动创建 SQLite 数据库：

```text
data/app.db
```

已初始化的主要表：

- `uploaded_file`
- `task_record`
- `taxonomy_version`
- `category_node`
- `diagnosis_issue`
- `adjustment_suggestion`
- `operation_log`

如果想手动查看数据库，可以安装 SQLite 命令行工具；运行项目本身不需要。

macOS 安装查看工具：

```bash
brew install sqlite
sqlite3 data/app.db
```

## 后续开发顺序

建议按 `dev-doc/00_分功能开发文档索引.md` 中的顺序继续：

1. Excel 上传与导入
2. 分类树解析与体系概览
3. 结构诊断
4. 向量索引与内容诊断
5. 智能建议生成
6. 人工审核
7. 动作执行与版本管理
8. 导出与诊断报告
9. 前端工作台

当前骨架已经为这些模块预留了后端目录和 API 入口。
