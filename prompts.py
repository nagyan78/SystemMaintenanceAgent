"""Prompt templates for LLM semantic checks."""

PARENT_CHILD_JUDGE_PROMPT = """你是产品分类体系治理专家。
请判断下面的父子分类关系是否可能错误挂载。

父节点名称：{parent_name}
子节点名称：{category_name}
完整路径：{path}
规则证据：{evidence}

请只基于分类语义判断，输出结构化结论。"""


SYNONYM_JUDGE_PROMPT = """你是产品分类体系治理专家。
请判断下面的同义词是否与标准分类节点语义一致。

标准节点名称：{category_name}
同义词字段：{synonyms}
完整路径：{path}
规则证据：{evidence}

请识别同义词是否可能错误、过宽、过窄或不是同义词，输出结构化结论。"""
