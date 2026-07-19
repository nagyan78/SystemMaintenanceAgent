from dataclasses import dataclass
from typing import Literal


IssueCategory = Literal["structure", "content"]


@dataclass(frozen=True, slots=True)
class IssueTypeDefinition:
    code: str
    label: str
    category: IssueCategory
    description: str


ISSUE_TYPES: dict[str, IssueTypeDefinition] = {
    item.code: item
    for item in (
        IssueTypeDefinition("missing_parent", "父节点缺失", "structure", "节点引用的父节点不存在，分类路径不完整。"),
        IssueTypeDefinition("excessive_depth", "层级过深", "structure", "节点所在分类路径超过允许的层级阈值。"),
        IssueTypeDefinition("excessive_width", "节点过宽", "structure", "节点直接子节点数量超过允许的宽度阈值。"),
        IssueTypeDefinition("duplicate_sibling", "同级重复", "structure", "同一父节点下存在名称重复的分类节点。"),
        IssueTypeDefinition("parent_child_redundancy", "父子命名重复", "structure", "父节点与子节点名称重复或表达冗余。"),
        IssueTypeDefinition("semantic_misplacement", "父子语义不匹配", "content", "节点语义与当前父节点的分类原则不一致。"),
        IssueTypeDefinition("inconsistent_dimension", "分类维度不一致", "content", "同一分类范围内混用了不同的分类维度。"),
        IssueTypeDefinition("synonym_format", "同义词格式错误", "content", "同义词列表存在格式、重复或自引用问题。"),
        IssueTypeDefinition("synonym_typo", "同义词拼写错误", "content", "同义词中存在可确认的拼写错误。"),
        IssueTypeDefinition("synonym_conflict", "同义词语义冲突", "content", "同义词包含与节点主名称不等价或冲突的概念。"),
        IssueTypeDefinition("synonym_overlap", "父子同义词重叠", "content", "父子节点的同义词范围发生重叠。"),
        IssueTypeDefinition("naming_nonstandard", "节点命名不规范", "content", "节点名称不符合命名规范或无法清晰表达分类边界。"),
        IssueTypeDefinition("semantic_duplicate", "语义重复", "content", "不同节点表达了高度相似或等价的分类语义。"),
        IssueTypeDefinition("unknown", "待确认问题", "content", "历史类型或来源不足以可靠映射，必须由 AI 重新分类并生成对应方案。"),
    )
}


# 仅允许语义明确的旧类型进入映射；读取历史数据时不得分析问题描述来猜类型。
LEGACY_ISSUE_TYPE_MAP: dict[str, str] = {
    "orphan": "missing_parent",
    "deep_level": "excessive_depth",
    "wide_node": "excessive_width",
    "bad_parent_child_relation": "semantic_misplacement",
    "inconsistent_granularity": "inconsistent_dimension",
    "synonym_format_issue": "synonym_format",
    "synonym_pollution": "synonym_conflict",
    "ambiguous_name": "naming_nonstandard",
    "naming_irregular": "naming_nonstandard",
    # 旧规则检查的是全局同名，不能证明“同级重复”或“语义重复”。
    "duplicate_name": "unknown",
}


def normalize_issue_type_code(value: str | None) -> str:
    raw = (value or "").strip()
    if raw in ISSUE_TYPES:
        return raw
    return LEGACY_ISSUE_TYPE_MAP.get(raw, "unknown")


def get_issue_type(value: str | None) -> IssueTypeDefinition:
    return ISSUE_TYPES[normalize_issue_type_code(value)]


def issue_type_metadata(value: str | None) -> dict[str, str]:
    definition = get_issue_type(value)
    return {
        "issue_type_code": definition.code,
        "issue_type_label": definition.label,
        "issue_category": definition.category,
    }


def legacy_values_for(code: str) -> tuple[str, ...]:
    canonical = normalize_issue_type_code(code)
    aliases = [raw for raw, mapped in LEGACY_ISSUE_TYPE_MAP.items() if mapped == canonical]
    return tuple(dict.fromkeys((canonical, *aliases)))
