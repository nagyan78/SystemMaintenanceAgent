# SystemMaintenanceAgent

标准产品体系维护与诊断工具。项目用于读取标准产品分类体系数据，自动检查树形结构中的层级、父子关系、节点宽度、重复命名、同义词和版本变化等问题，并生成可读的诊断报告。

## 功能概览

- 标准产品体系结构诊断：检查层级过深、节点过宽、父节点缺失、孤立节点等问题。
- 节点命名与关系检查：发现重复名称、父子节点同名、疑似不合理的父子关系。
- 同义词检查：识别缺失同义词、疑似异常同义词等问题。
- 质量评估：输出节点数量、结构复杂度、问题数量等量化指标。
- 版本对比：对比两份体系数据，识别新增、删除和变更内容。
- 报告生成：支持 Markdown、JSON 和 HTML 看板输出。
- 本地上传诊断：提供浏览器上传 `.xlsx` 文件的本地页面，便于快速查看诊断结果。

## 项目结构

```text
.
├── main.py                    # 完整诊断命令行入口
├── src/
│   ├── advanced/              # 完整诊断流水线：规则检查、LLM 判断、版本对比、报告输出
│   ├── common.py              # 第一轮诊断共享常量和问题数据结构
│   ├── main.py                # 第一轮结构诊断入口
│   ├── data_loader.py         # Excel 数据读取与字段标准化
│   ├── structure_checker.py   # 父节点、深度、宽度等结构规则检查
│   ├── tree_builder.py        # 生成树路径、深度、子节点数量等辅助字段
│   ├── tree_analyzer.py       # 汇总树结构指标
│   ├── web_app.py             # 本地上传诊断网页
│   └── report_generator.py    # Markdown/HTML 看板生成
├── data/
│   └── sample_products.csv    # 示例数据
├── tests/                     # 单元测试
├── requirements.txt
└── start_upload_frontend.bat  # Windows 一键启动上传诊断页面
```

## 环境要求

- Python 3.10 或更高版本
- Windows、macOS 或 Linux
- 依赖库见 `requirements.txt`

安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

macOS/Linux：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 数据格式

完整诊断入口 `main.py` 调用 `src/advanced/` 中的诊断流水线，支持 `.csv`、`.xlsx`、`.xls` 文件。

基础必需字段：

| 字段名 | 说明 |
| --- | --- |
| `category_id` | 当前分类节点 ID |
| `category_name` | 当前分类节点名称 |
| `parent_id` | 父节点 ID |

可选字段：

| 字段名 | 说明 |
| --- | --- |
| `synonyms` | 同义词，多个值可用逗号分隔 |
| `version` | 版本标识 |

如果源数据使用其他字段名，程序也支持部分常见别名，例如 `id`、`name`、`parent`、`pid`、`alias`、`syn_list` 等。

`src` 下的第一轮结构诊断入口主要面向 `.xlsx` 文件，要求包含以下字段：

| 字段名 | 说明 |
| --- | --- |
| `category_id` | 当前分类节点 ID |
| `category_name` | 当前分类节点名称 |
| `category_group_id` | 父级或分组 ID |
| `category_pids` | 父级路径 |
| `category_group_name` | 父级或分组名称 |
| `syn_list` | 同义词列表 |

## 使用方式

### 1. 运行完整诊断

```powershell
python main.py --input data/sample_products.csv --output output/report.md
```

自定义规则阈值：

```powershell
python main.py --input data/sample_products.csv --output output/report.md --max-depth 8 --max-children 2000
```

进行版本对比：

```powershell
python main.py --input data/new_products.xlsx --compare data/old_products.xlsx --output output/version_report.md
```

运行后会生成：

- Markdown 报告：例如 `output/report.md`
- JSON 报告：与 Markdown 报告同名的 `.json` 文件

### 2. 运行第一轮结构诊断

```powershell
python -m src.main --input data/your_products.xlsx
```

指定输出位置：

```powershell
python -m src.main --input data/your_products.xlsx --output outputs/reports/diagnosis_report.md --html-output outputs/reports/diagnosis_dashboard.html
```

### 3. 启动本地上传诊断页面

Windows 可以直接双击：

```text
start_upload_frontend.bat
```

或在命令行运行：

```powershell
python -m src.web_app --host 127.0.0.1 --port 8765 --open-browser
```

浏览器打开后，上传 `.xlsx` 文件即可生成结构诊断看板。上传文件只会被本地临时读取，不会写回修改原始 Excel 文件。

## LLM 语义检查配置

完整诊断入口支持可选的 LLM 语义检查。如果不配置模型，程序仍会执行规则检查。

复制 `.env.example` 为 `.env`，然后填写模型配置：

```env
MODEL_PROVIDER=openai
MODEL_NAME=gpt-4o-mini
OPENAI_API_KEY=your_api_key_here
```

也可以使用 Google 模型配置：

```env
MODEL_PROVIDER=google_genai
MODEL_NAME=gemini-1.5-flash
GOOGLE_API_KEY=your_api_key_here
```

## 运行测试

```powershell
pytest
```

## Git 提交建议

提交到 GitHub 前，建议忽略本地环境、缓存和输出文件：

```gitignore
.venv/
__pycache__/
*.pyc
.env
output/
outputs/
```

常用提交流程：

```powershell
git status
git add .
git commit -m "Initial commit"
git branch -M main
git push -u origin main
```

## 适用场景

- 标准产品分类体系维护
- 分类树结构质量检查
- 产品类目治理与版本留痕
- 分类体系调整前后的质量对比
- 批量发现分类节点冗余、缺失、不平衡等问题

## License

This project is for course and prototype use. Add a license file before publishing it as an open-source project.
