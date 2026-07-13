# PRD-03 版本 Diff 可视化（D1）

> 状态：PARTIAL / PLANNED  
> 路线归属：R2/R3。后端 Diff service/API 和前端基础选择能力已存在；完整过滤、树高亮和路径展示尚未完成。

- **文档编号**：PRD-03
- **名称**：版本 Diff 可视化（多版本迭代对比）
- **状态**：待评审
- **作者**：调度达（AgentsOrchestrator）
- **日期**：2026-07-09
- **历史关联方案**：[功能增强脑暴与优先级](../99_历史归档/历史方案/功能增强脑暴与优先级.md)（D1）、[审核多轮与版本续跑修复方案](../99_历史归档/历史方案/审核多轮与版本续跑修复方案.md)；当前 schema 为 `backend/app/schemas/version.py::VersionDiff`

---

## 1. 背景与问题

版本链在 PRD-01 落地后将真正连续（v1.0 → v1.1 → v1.2），但当前**版本只是数据库里的数字**——用户感知不到"这一版到底改了什么"。`schemas/version.py:46` 已定义 `VersionDiff`（added/deleted/renamed/moved/synonym_changed），但**后端 service + API 已落地**——`VersionService.get_version_diff`（version_service.py:103-164）按 `category_id` 对齐两版、分类五类变更；路由 `GET /api/versions/{version_id}/diff?target_version_id=`（versions.py:31）与 `POST /api/versions/{version_id}/rollback`（versions.py:43）均已实现。**唯一缺口是前端 Diff 视图**，用户仍感知不到迭代。

---

## 2. 目标与范围

### 目标
- G1：对任意两个版本（from/to）计算结构化 Diff：新增、删除、改名、移动（父节点变化）、同义词变更。
- G2：前端以**可读、可筛选、可跳转**的方式呈现 Diff（树/列表双视图，按变更类型过滤）。
- G3：在审核/版本页直接对比"本轮批准前 vs 批准后"，让迭代可见。

### 成功指标
- 对 demo 数据构造 v1.0→v1.1（含增/删/改父/改同义词各若干），Diff 五类变更 100% 命中。
- 前端可在 ≤2 次点击内定位任一变更节点并高亮其树位置。

### 范围内 / 外
- **内**：验证现有 Diff 计算、`GET /api/versions/{from_version_id}/diff?target_version_id={to_version_id}`、前端 Diff 视图。
- **外**：Diff 自动生成"自然语言报告"（D3 另案）、批量版本对比（>2 版）。

---

## 3. 用户角色与场景

- **维护员**：本轮批准了 8 条建议，想确认"实际落库改了哪些节点" → 打开 v1.0→v1.1 Diff，看到 3 新增 / 2 改名 / 3 移动。
- **主管/审计**：抽查"v1.1 相对 v1.0 有没有误删重要类目" → 过滤 `deleted` 类型，逐条核对。
- **架构师**：评估"同义词补全是否生效" → 过滤 `synonym_changed`。

---

## 4. 功能需求（FR）

| 编号 | 需求 | 优先级 |
|------|------|--------|
| FR-1 | 验证 `VersionService.get_version_diff(from_id, to_id)` 已正确实现五类变更（added/deleted/renamed/moved/synonym_changed） | P0 |
| FR-2 | 验证 `GET /api/versions/{version_id}/diff?target_version_id=` 返回结构与 `VersionDiff` 一致 | P0 |
| FR-3 | 前端 `VersionDiffView`：左右/上下双栏展示 from→to；按变更类型 Tab 过滤（**本 PRD 核心新增**） | P0 |
| FR-4 | 每个变更项可点击 → 在分类树中高亮对应节点（复用 `TaxonomyTreeView`） | P1 |
| FR-5 | 展示五类变更的汇总数量，并支持按变更类型过滤 | P1 |
| FR-6 | 版本页提供"对比选择器"（选 from/to），默认当前版 vs 上一版 | P1 |
| FR-7 | Diff 项展示路径变化（moved 显示"从 A/B/C → A/D/C"） | P2 |

---

## 5. 现有资产与改动点

- **复用（已验证）**：
  - `backend/app/schemas/version.py::VersionDiff`（:46）字段齐备：`added/deleted/renamed/moved/synonym_changed`，每项 `list[dict]`。
  - `TaxonomyRepository.list_nodes(version_id)`（被 vector_index_service 使用）—— 取某版本全量节点用于比对。
  - `VersionRecord`（id/file_id/version_no/description/created_time）—— 选择器展示。
  - 节点字段（`TaxonomyNodeRecord`）：category_id/name/parent_id/level/path_ids/path_names/syn_list/is_leaf。
- **新增/改动（后端已就绪，仅前端待建）**：
  - `backend/app/version_service.py::get_version_diff`（已存在，lines 103-164）— 按 category_id 对齐两版，分类五类变更。
  - `backend/app/api/versions.py:31` `GET /{version_id}/diff?target_version_id=`（已存在）— 直接复用。
  - `backend/app/api/versions.py:43` `POST /{version_id}/rollback`（已存在）— 回滚也现成。
  - **本 PRD 重点（待新增）**：
    - `frontend/src/api/versions.ts`：新增 `getVersionDiff(fromId, toId)` 调上述 API。
    - `frontend/src/views/VersionDiffView.vue`：Diff 展示 + 过滤 + 跳树高亮。

---

## 6. 接口设计（草案）

```http
GET /api/versions/35/diff/37
→ {
  "from_version_id": 35,
  "to_version_id": 37,
  "added":     [{"category_id": 2001, "category_name": "智能眼镜", "parent_id": 50}],
  "deleted":   [{"category_id": 1990, "category_name": "老式眼镜"}],
  "renamed":   [{"category_id": 1880, "from_name": "耳机", "to_name": "音频耳机"}],
  "moved":     [{"category_id": 1880, "from_parent": 40, "to_parent": 55, "from_path":"电子产品/配件", "to_path":"电子产品/音频设备"}],
  "synonym_changed": [{"category_id": 1880, "from_syn":"耳麦", "to_syn":"耳麦,头戴耳机"}]
}
```

---

## 7. 前端交互

- 版本列表/详情页新增「对比」按钮 → 进入 `VersionDiffView`。
- 顶部两个下拉选 from/to（默认当前版与上一版）。
- 主体：左侧变更类型 Tab（全部/新增/删除/改名/移动/同义词），右侧列表；点击某项 → 弹层或跳转树视图高亮 `category_id`。
- 数字徽标显示每类变更数量，一眼看清"这版动了什么"。

---

## 8. 验收标准

- AC-1：`GET /api/versions/{from}/diff/{to}` 返回结构符合 `VersionDiff`，五类变更分类正确。
- AC-2：构造的 demo 双版本（含各类型）Diff 命中率 100%。
- AC-3：前端可筛选任一类变更，点击项可高亮树节点。
- AC-4：from/to 颠倒时（to 作为 from）结果对称（added↔deleted）。
- AC-5：回归 `pytest backend/tests` 全绿；`npm run test:contract` 通过。

---

## 9. 依赖与里程碑

- **依赖**：Diff 计算本身不依赖 PRD-01 循环节点（纯确定性比对，后端已就绪）。但**多版本"迭代"体验**依赖 PRD-01 把版本链做连续（否则你只有 v1.0 和它的单次 v1.1，没东西可比）。建议：PRD-01 先行 → 本 PRD 前端紧随。
- **里程碑**：
  - PR1：FR-1/2 验证现有后端 diff/API（补单测覆盖 demo 双版本）。
  - PR2：FR-3/4/5/6 前端 Diff 视图 + 跳树 + 版本选择器。
  - PR3：FR-7 路径变化展示。

---

## 10. 风险与对策

| 风险 | 对策 |
|------|------|
| 两版节点量巨大（2 万级）比对慢 | 仅在用户请求 Diff 时按需计算；`category_id` 建索引；可异步+进度 |
| renamed 与 moved 边界模糊 | 明确优先级：parent_id 变优先判 moved；仅 name 变判 renamed |
| from/to 跨文件无意义 | API 校验两版本同 `file_id`，否则 400 |

---

## 11. 非功能性要求

- Diff 计算为纯确定性比对，不调用 LLM，成本低、可复现。
- 大版本比对异步化（可选），避免前端阻塞。
- 与原 Excel 只读约束一致，Diff 不影响任何版本数据。
