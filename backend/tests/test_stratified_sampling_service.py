from backend.app.services.stratified_sampling_service import StratifiedSamplingService


def _nodes():
    nodes = []
    category_id = 1
    for root_id in (100, 200, 300):
        for level in (1, 2, 3, 4):
            for is_leaf in (0, 1):
                for has_synonyms in (0, 1):
                    for _ in range(8):
                        nodes.append({
                            "category_id": category_id,
                            "category_name": f"节点{category_id}",
                            "parent_id": None if level == 1 else root_id,
                            "path_ids": f"{root_id},{category_id}",
                            "path_names": f"根{root_id} > 节点{category_id}",
                            "level": level,
                            "is_leaf": is_leaf,
                            "syn_list": "同义词" if has_synonyms else None,
                        })
                        category_id += 1
    return nodes


def test_joint_stratified_sample_is_exact_unique_and_reproducible():
    service = StratifiedSamplingService()
    first = service.select(_nodes(), sample_size=200, seed=42)
    second = service.select(list(reversed(_nodes())), sample_size=200, seed=42)

    assert len(first) == 200
    assert len({item["category_id"] for item in first}) == 200
    assert [item["category_id"] for item in first] == [item["category_id"] for item in second]
    assert {item["sampling"]["root_category_id"] for item in first} == {100, 200, 300}
    assert all(item["sampling"]["random_seed"] == 42 for item in first)


def test_sample_uses_all_nodes_when_population_is_smaller():
    nodes = _nodes()[:20]

    selected = StratifiedSamplingService().select(nodes, sample_size=200, seed=7)

    assert [item["category_id"] for item in selected] == [item["category_id"] for item in nodes]
