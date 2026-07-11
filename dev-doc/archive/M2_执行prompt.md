# M2 里程碑执行 Prompt

> **历史执行材料（ARCHIVED）**：不得直接作为当前开发 prompt 使用。当前事实和路线见 `CURRENT_IMPLEMENTATION.md`、`ROADMAP.md`。

> 用途：先完成"环境准备"，再把"复制以下内容作为 Prompt"代码块整体复制给 AI 编程助手，启动 M2 代码实现。
> 项目路径：/Users/flflfl/Documents/code/SystemMaintenanceAgent
> 技术方案：LLM 用 DeepSeek API（OpenAI 兼容），Embedding 用通义千问 DashScope（OpenAI 兼容），统一 langchain-openai

---

## 一、环境准备（开工前必做）

M2 需要三个外部依赖：Qdrant（向量数据库）+ DeepSeek API（LLM）+ 千问 embedding API。当前环境状态：

| 组件 | 状态 | 需要操作 |
|------|------|---------|
| Docker | 已安装 29.4.3 | 启动 Docker Desktop |
| Qdrant | 未运行 | docker run 启动 |
| DeepSeek API | 需要 API key | 获取 key |
| 千问 embedding API | 需要 API key | 获取 DashScope key |
| langchain-openai | 未安装 | pip install |
| qdrant-client | 未安装 | pip install |

### 步骤 1：启动 Docker Desktop

打开 Docker Desktop 应用，等待左下角图标变绿。验证：
```bash
docker info | grep "Server Version"
```

### 步骤 2：启动 Qdrant

```bash
mkdir -p data/qdrant
docker run -d --name qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v $(pwd)/data/qdrant:/qdrant/storage \
  qdrant/qdrant
```

验证：
```bash
curl http://localhost:6333/
```

### 步骤 3：获取 API Key

**DeepSeek API key**：
- 访问 https://platform.deepseek.com/ 注册并创建 API key
- 模型名：`deepseek-chat`
- Base URL：`https://api.deepseek.com`

**千问（DashScope）API key**：
- 访问 https://dashscope.console.aliyun.com/ 注册并创建 API key
- Embedding 模型名：`text-embedding-v2`
- Base URL：`https://dashscope.aliyuncs.com/compatible-mode/v1`

### 步骤 4：配置环境变量

在项目根目录创建 `.env` 文件（已在 .gitignore 中）：
```bash
DEEPSEEK_API_KEY=sk-你的deepseek密钥
DASHSCOPE_API_KEY=sk-你的千问密钥
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=taxonomy_nodes
```

### 步骤 5：安装 Python 依赖

```bash
.venv/bin/pip install langchain-openai qdrant-client
```

> 不再需要 langchain-ollama（可以从 requirements.txt 移除）

### 步骤 6：验证全部就绪

```bash
curl http://localhost:6333/                    # Qdrant
.venv/bin/python -c "
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
llm = ChatOpenAI(model='deepseek-chat', base_url='https://api.deepseek.com', api_key='你的key')
print(llm.invoke('你好').content[:20])
emb = OpenAIEmbeddings(model='text-embedding-v2', base_url='https://dashscope.aliyuncs.com/compatible-mode/v1', api_key='你的key')
print(len(emb.embed_query('测试')))
"
```

---

## 二、复制以下内容作为 Prompt

```
你是一个资深 Python 后端工程师，现在要在现有项目上实现 M2 里程碑：向量索引 + 内容诊断智能体。这是项目从"工作流"变成"智能体"的转折点。

## 项目背景
项目名：产品标准体系维护智能体（FastAPI + LangGraph + LangChain + SQLite + Qdrant）。
M1 已完成：graph 的 5 个确定性节点（parse_excel/build_tree/save_version/structure_diagnosis/report）已接真实 service，19 个测试全部通过。
M2 目标：实现内容诊断的 Agent Loop，体现 LLM 决策 + tool calling + ReAct 循环。

## LLM 与 Embedding 方案（重要）
- **Chat LLM**：DeepSeek API，用 langchain-openai 的 ChatOpenAI，base_url="https://api.deepseek.com"，model="deepseek-chat"
- **Embedding**：通义千问 DashScope，用 langchain-openai 的 OpenAIEmbeddings，base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"，model="text-embedding-v2"
- 两者都是 OpenAI 兼容格式，统一用 langchain-openai，不用 langchain-ollama
- API key 从环境变量读取：DEEPSEEK_API_KEY、DASHSCOPE_API_KEY（用 python-dotenv 加载 .env）
- requirements.txt 移除 langchain-ollama，添加 langchain-openai + qdrant-client

## 必读文档（开工前先读，不要跳过）
1. dev-doc/00_开发里程碑索引.md — 读 §5 M2 章节（文件清单/数据结构/接口契约/实现顺序/验收标准/禁止行为）
2. dev-doc/04_向量索引与内容诊断开发设计.md — 读 §11 内容诊断 Agent Loop 设计
3. dev-doc/10_LangGraph智能体工作流开发设计.md — 读 §8.6 diagnosis_planning_node、§8.7 content_diagnosis_node（Agent Loop）、§13 Tool calling
4. backend/app/config.py — 现有配置（已有 qdrant_url/qdrant_collection，需补 deepseek/dashscope 配置）
5. backend/app/agents/nodes.py — 现有 M1 节点实现（看 _complete_step 模式，M2 节点保持一致风格）
6. backend/app/agents/states.py — State 定义（M2 需加 diagnosis_plan 字段）

## M2 涉及节点（3 个）
| 节点 | 性质 | 调用的 service |
|------|------|---------------|
| index_vector_node | 工作流·确定性 | vector_index_service.index_version(version_id) |
| diagnosis_planning_node | 智能体·LLM规划 | DiagnosisPlanningAgent.run(structure_stats, tree_overview) |
| content_diagnosis_node | 智能体·ReAct loop | ContentDiagnosisAgent.run(version_id, plan) |

> diagnosis_planning_node 为新增节点，位于 structure_diagnosis_node 之后、content_diagnosis_node 之前。

## 文件清单（新建/修改）
新建：
- backend/app/vectorstores/qdrant_store.py（Qdrant collection/index/search）
- backend/app/services/vector_index_service.py（向量索引服务）
- backend/app/services/content_diagnosis_service.py（内容诊断 Agent Loop 封装）
- backend/app/tools/tree_tools.py（4 个 @tool 函数）
- backend/app/agents/prompts.py（内容诊断 system prompt + few-shot）

修改：
- backend/app/config.py（加 deepseek_api_key/base_url/model + dashscope_api_key/embedding_base_url/embedding_model）
- backend/app/agents/states.py（加 diagnosis_plan 字段）
- backend/app/agents/nodes.py（替换 index_vector/content_diagnosis 硬编码 + 新增 diagnosis_planning_node）
- backend/app/agents/graph.py（在 structure_diagnosis 后插入 diagnosis_planning_node）
- backend/app/repositories/taxonomy_repo.py（补节点详情/路径/子节点查询方法）
- requirements.txt（移除 langchain-ollama，加 langchain-openai + qdrant-client）

## 数据结构

### Qdrant Collection
Collection: taxonomy_nodes
Point ID: {version_id}_{category_id}
Vector: 千问 text-embedding-v2 输出（1536 维）

### config.py 新增字段
deepseek_api_key: str = ""  # 从环境变量 DEEPSEEK_API_KEY 读取
deepseek_base_url: str = "https://api.deepseek.com"
deepseek_model: str = "deepseek-chat"
dashscope_api_key: str = ""  # 从环境变量 DASHSCOPE_API_KEY 读取
embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
embedding_model: str = "text-embedding-v2"

### 内容诊断结构化输出 schema
class ContentDiagnosisOutput(BaseModel):
    is_issue: bool
    issue_type: Literal["synonym_pollution","semantic_duplicate","bad_parent_child_relation","inconsistent_granularity","naming_irregular"] | None = None
    abnormal_synonyms: list[str] = Field(default_factory=list)
    reason: str = ""
    risk_level: Literal["low", "medium", "high"] = "low"
    confidence: float = 0.0

### diagnosis_planning_node 输出
class DiagnosisPlan(BaseModel):
    priority_subtrees: list[str] = Field(default_factory=list)
    sample_strategy: Literal["focused", "full_scan", "sampling"] = "focused"
    focus_issues: list[str] = Field(default_factory=list)
    estimated_candidates: int = 200

## 接口契约

### Tool 函数签名（供 LangChain tool calling 使用）
@tool
def get_node_detail(version_id: int, category_id: int) -> dict:
    """查询单个节点详情：名称、路径、同义词、层级、是否叶子"""

@tool
def get_node_path(version_id: int, category_id: int) -> str:
    """查询节点完整路径（path_names）"""

@tool
def get_children(version_id: int, parent_id: int) -> list[dict]:
    """查询直接子节点列表"""

@tool
def search_similar_nodes(version_id: int, node_text: str, top_k: int = 10) -> list[dict]:
    """Qdrant 语义召回，返回相似节点列表"""

@tool
def submit_diagnosis(issue: dict) -> str:
    """提交一条诊断结果，返回 issue_id"""

### Service 函数签名
# vector_index_service
def index_version(version_id: int) -> IndexResult: ...

# content_diagnosis_service（封装 Agent Loop）
class ContentDiagnosisAgent:
    def run(self, version_id: int, plan: DiagnosisPlan) -> list[ContentIssue]: ...

# diagnosis_planning（也封装为 agent）
class DiagnosisPlanningAgent:
    def run(self, structure_stats: dict, tree_overview: dict) -> DiagnosisPlan: ...

### LLM 实例化方式
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

llm = ChatOpenAI(
    model=settings.deepseek_model,
    base_url=settings.deepseek_base_url,
    api_key=settings.deepseek_api_key,
    temperature=0.1,
)
embeddings = OpenAIEmbeddings(
    model=settings.embedding_model,
    base_url=settings.embedding_base_url,
    api_key=settings.dashscope_api_key,
)

## 实现顺序（严格按此顺序）
1. 更新 requirements.txt（移除 langchain-ollama，加 langchain-openai + qdrant-client）
2. 更新 config.py（加 deepseek + dashscope 配置，用 python-dotenv 加载 .env）
3. 实现 vectorstores/qdrant_store.py（create_collection / index_nodes / search_similar）
4. 实现 services/vector_index_service.py（index_version，用千问 embedding 向量化节点文本写入 Qdrant）
5. 实现 tools/tree_tools.py 中的 4 个 @tool 函数（get_node_detail/get_node_path/get_children/search_similar_nodes）
6. 补充 repositories/taxonomy_repo.py（节点详情/路径/子节点查询方法）
7. 编写 agents/prompts.py（内容诊断 system prompt + few-shot examples + 诊断规划 prompt）
8. 实现 services/content_diagnosis_service.py（用 create_react_agent 或手写 ReAct loop 封装 ContentDiagnosisAgent）
9. 实现 diagnosis_planning 逻辑（DiagnosisPlanningAgent，LLM 看结构统计后输出 DiagnosisPlan）
10. 修改 agents/states.py（加 diagnosis_plan 字段）
11. 修改 agents/nodes.py：替换 index_vector_node 和 content_diagnosis_node 硬编码 + 新增 diagnosis_planning_node
12. 修改 agents/graph.py：在 structure_diagnosis_node 后插入 diagnosis_planning_node
13. 编写 M2 集成测试

> 依赖关系：1-2（依赖+配置）→ 3-4（Qdrant 基础设施）→ 5-6（Tool+Repo）→ 7-9（Prompt+Agent）→ 10-12（State+Node+Graph）→ 13

## Agent Loop 设计要点

### ContentDiagnosisAgent（ReAct loop）
对每个候选节点（来自结构诊断结果 + 同义词非空节点）：
1. [Thought] 分析候选节点
2. [Action] 调用 search_similar_nodes(node_text) 召回相似节点
3. [Observation] 获得相似节点列表
4. [Thought] 判断是否需要查父节点路径
5. [Action] 调用 get_node_path(node_id) 获取路径
6. [Observation] 获得完整路径
7. [Thought] 综合判断是否存在语义问题
8. [Action] 调用 submit_diagnosis(issue) 提交诊断
9. 如果还有候选节点，回到步骤 1

### DiagnosisPlanningAgent
输入：结构诊断统计（44 个缺失父节点、225 个过宽子节点等）+ 12 个一级类目概览
LLM 任务：决定内容诊断的优先级和范围
输出 DiagnosisPlan：priority_subtrees / sample_strategy / focus_issues / estimated_candidates

## 验收标准（全部要满足）
1. Qdrant 索引 21090 个节点成功（indexed_count = 21090）
2. 内容诊断能识别"苹果"同义词污染（AirPods/iPhone 等）
3. LLM 通过 tool calling 自主查询节点信息（非硬编码，日志可见 tool 调用记录）
4. 可以在日志中看到 ReAct 循环的 Thought-Action-Observation 链
5. content_issue_count 来自真实 LLM 判断（非硬编码 2）
6. diagnosis_planning_node 输出了 DiagnosisPlan，内容诊断基于 plan 执行

## 禁止行为（硬约束，违反即返工）
- 禁止在 content_diagnosis_node 中直接调 LLM 做单次判断——必须走 Agent Loop
- 禁止在 node 函数中拼 prompt——prompt 在 agents/prompts.py 中管理
- 禁止在 node 函数中直接操作 Qdrant——通过 service + tool
- 禁止让 LLM 直接写 diagnosis_issue 表——LLM 通过 submit_diagnosis tool 提交，由 service 写库
- 禁止全量扫描 21090 个节点做内容诊断——必须先经 diagnosis_planning_node 规划
- 禁止 node 函数超过 30 行
- 禁止使用 langchain-ollama 或 Ollama——用 DeepSeek API + langchain-openai

## 完成后
1. 运行 pytest 确保全部测试通过（含 M1 的 19 个回归测试）
2. 启动 Qdrant + 配好 .env 后，用样例 Excel 实际跑一遍 workflow
3. 检查日志中有 Thought-Action-Observation 链
4. 输出代码摘要：列出新建/修改的文件和每个文件的核心函数
```
