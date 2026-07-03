"""Prompt templates for LLM semantic checks."""

COMMON_OUTPUT_RULES = """你的任务不是复述规则检测结果，而是从给定节点信息中提取真正需要语义分析的节点名称，并判断这些节点之间是否存在分类体系问题。

请只输出 JSON：
{
  "is_problem": true 或 false,
  "confidence": 0到1之间的小数,
  "relevant_nodes": ["节点1", "节点2", "节点3"],
  "semantic_relation": "说明这些节点之间的语义关系",
  "reason": "只写语义原因，不要写规则原因",
  "suggestion": "只写基于语义的修改建议，如果不确认问题则写无需调整或建议人工复核"
}

不要输出“分支爆炸比超标”“节点数量远超平均宽度”“叶子节点占比为100%”“父节点名称包含子节点名称”“建议增加中间分组”等规则复述内容。"""


PARENT_CHILD_JUDGE_PROMPT = """你是一个产品分类体系语义诊断助手。

父节点名称：{parent_name}
子节点名称：{category_name}
完整路径节点：{path}

请判断父子节点之间是否存在业务上的上下位关系，是否存在层级冗余、粒度不一致或语义不匹配。
例如“光模块 / 单模光模块”通常是合理上下位分类，不应仅因为名称包含就确认问题。

{output_rules}"""


SYNONYM_JUDGE_PROMPT = """你是一个产品分类体系语义诊断助手。

标准节点名称：{category_name}
同义词字段：{synonyms}
完整路径节点：{path}

请判断同义词是否与标准名称重复，或是否属于别名、简称、英文名、无效冗余。

{output_rules}"""
