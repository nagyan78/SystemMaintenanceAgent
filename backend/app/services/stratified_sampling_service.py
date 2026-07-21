import hashlib
import math
import random
from collections import defaultdict
from typing import Any


class StratifiedSamplingService:
    """按分类树业务维度生成可复现的不放回样本。"""

    def select(
        self,
        nodes: list[dict[str, Any]],
        *,
        sample_size: int = 200,
        seed: int = 20260721,
    ) -> list[dict[str, Any]]:
        ordered = sorted(nodes, key=lambda item: int(item["category_id"]))
        target = min(max(int(sample_size), 0), len(ordered))
        if target == 0:
            return []
        if target == len(ordered):
            return [self._annotate(item, seed) for item in ordered]

        by_root: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in ordered:
            by_root[self._root_key(node)].append(node)

        selected_ids: set[int] = set()
        # 根分类数量可能超过样本预算，此时按根键稳定抽取能够覆盖的根。
        root_keys = sorted(by_root, key=self._sort_key)
        if len(root_keys) > target:
            root_keys = self._sample(root_keys, target, seed, "roots")
        for root_key in root_keys:
            chosen = self._sample(by_root[root_key], 1, seed, f"root:{root_key}")[0]
            selected_ids.add(int(chosen["category_id"]))

        remaining_slots = target - len(selected_ids)
        remaining = [item for item in ordered if int(item["category_id"]) not in selected_ids]
        cells: dict[tuple[str, int, int, int], list[dict[str, Any]]] = defaultdict(list)
        for node in remaining:
            cells[self._stratum(node)].append(node)

        quotas = self._allocate(cells, remaining_slots)
        for key in sorted(cells, key=self._sort_key):
            for node in self._sample(cells[key], quotas.get(key, 0), seed, f"cell:{key}"):
                selected_ids.add(int(node["category_id"]))

        selected = [item for item in ordered if int(item["category_id"]) in selected_ids]
        return [self._annotate(item, seed) for item in selected]

    def _allocate(
        self,
        cells: dict[tuple[str, int, int, int], list[dict[str, Any]]],
        slots: int,
    ) -> dict[tuple[str, int, int, int], int]:
        if slots <= 0 or not cells:
            return {key: 0 for key in cells}
        total = sum(len(items) for items in cells.values())
        raw = {key: slots * len(items) / total for key, items in cells.items()}
        quotas = {key: min(len(cells[key]), math.floor(value)) for key, value in raw.items()}
        remaining = slots - sum(quotas.values())
        ranked = sorted(
            cells,
            key=lambda key: (-(raw[key] - math.floor(raw[key])), self._sort_key(key)),
        )
        while remaining > 0:
            progressed = False
            for key in ranked:
                if quotas[key] >= len(cells[key]):
                    continue
                quotas[key] += 1
                remaining -= 1
                progressed = True
                if remaining == 0:
                    break
            if not progressed:
                break
        return quotas

    def _annotate(self, node: dict[str, Any], seed: int) -> dict[str, Any]:
        result = dict(node)
        root_key, level, is_leaf, has_synonyms = self._stratum(node)
        result["sampling"] = {
            "root_category_id": int(root_key) if root_key.isdigit() else root_key,
            "level": level,
            "is_leaf": bool(is_leaf),
            "has_synonyms": bool(has_synonyms),
            "random_seed": seed,
        }
        return result

    def _stratum(self, node: dict[str, Any]) -> tuple[str, int, int, int]:
        return (
            self._root_key(node),
            int(node.get("level") or 0),
            int(bool(node.get("is_leaf"))),
            int(self._has_synonyms(node.get("syn_list"))),
        )

    @staticmethod
    def _root_key(node: dict[str, Any]) -> str:
        path_ids = str(node.get("path_ids") or "")
        ids = [part.strip().strip("[]") for part in path_ids.split(",") if part.strip().strip("[]") not in {"", "-1"}]
        return ids[0] if ids else str(node["category_id"])

    @staticmethod
    def _has_synonyms(value: Any) -> bool:
        return str(value or "").strip() not in {"", "[]", "[null]", "null"}

    @staticmethod
    def _sort_key(value: Any) -> str:
        return repr(value)

    def _sample(self, values: list[Any], size: int, seed: int, scope: str) -> list[Any]:
        if size <= 0:
            return []
        if size >= len(values):
            return list(values)
        digest = hashlib.sha256(f"{seed}:{scope}".encode("utf-8")).digest()
        rng = random.Random(int.from_bytes(digest[:8], "big"))
        positions = sorted(rng.sample(range(len(values)), size))
        return [values[index] for index in positions]
