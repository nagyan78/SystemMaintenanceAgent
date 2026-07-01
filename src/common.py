"""第一轮结构诊断流程共用的常量和数据结构。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# 第一轮诊断面向标准产品体系 Excel。这里要求字段相对严格，是为了确保
# 后续能稳定构造树结构：节点 ID、节点名称、父级路径、父级名称和同义词
# 信息都要存在。
REQUIRED_COLUMNS: tuple[str, ...] = (
    "category_id",
    "category_name",
    "category_group_id",
    "category_pids",
    "category_group_name",
    "syn_list",
)

# 这些字段本质上是“标识符”，不是数学数字。Excel 可能把 1001 保存为
# 1001.0，所以读取后要统一转回稳定的字符串 ID。
ID_COLUMNS: tuple[str, ...] = (
    "category_id",
    "category_group_id",
    "category_pids",
)

# 默认规则阈值。后续如果要把阈值做成命令行参数，可以优先改这里或在入口
# 层传入覆盖值。
DEFAULT_DEPTH_THRESHOLD = 8
DEFAULT_WIDTH_THRESHOLD = 100


@dataclass(frozen=True)
class IssueResult:
    """一条标准化的诊断问题记录。

    所有规则检查都返回这个结构，报告生成器只需要读取统一字段即可。
    这样以后新增“命名问题”“同义词问题”等规则时，不需要重写报告逻辑。
    """

    issue_type: str
    node_id: str
    node_name: str
    path: str
    severity: str
    reason: str
    suggestion: str
    confidence: float
    need_manual_review: bool

    def to_dict(self) -> dict[str, object]:
        """转换为普通字典，方便后续导出 JSON 或写入报告。"""

        return asdict(self)
