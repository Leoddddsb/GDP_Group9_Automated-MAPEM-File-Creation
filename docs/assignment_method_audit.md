# Assignment 方法筛选记录

这份笔记只记录 lane assignment 方法的调试、对比和筛选过程。它不放进 `file_extraction.md` / `file_extraction_ch.md` 主笔记，因为这些内容属于实验记录，不是 Step 2 的核心使用说明。

## 目的

我们要比较几种把 extracted facts 匹配到 CAD lane 的方法，判断哪一种在当前本地数据里最有效、最安全，并且给出实际 site 示例，方便人工审核。

测试过的方法：

1. `cad_context_validation`
2. `cad_movement_label_nearest_lane`
3. `semantic_movement_to_cad_lane_bridge`
4. `cad_signal_arrow_direction_match`
5. `semantic_movement_lane_proxy`
6. `pdf_same_page_assignment`
7. `pdf_to_cad_transform_required`
8. `gis_to_cad_transform_required`

这些方法的统计会写入 `geometry_assignments.partial.json` 的 `assignment_method_audit[]`。每个方法包含：

- `method`
- `status`
- `matched_count`
- `candidate_count`
- `examples[]`
- `notes`

## 当前结论

| 方法 | 当前结果 | 解释 |
| --- | --- | --- |
| `cad_context_validation` | 有效 | 当前最有效。它在同一个 CAD modelspace 里，用 stop line、signal head、arrow、CAD block/text、pole、road marking 等上下文证据确认 heuristic CAD lanes。 |
| `cad_movement_label_nearest_lane` | 当前 337L / 950L 不作为主方法 | 有候选，但实际例子多来自 key / legend / notes 图层，容易把图例文字误当成真实 lane movement label。 |
| `semantic_movement_to_cad_lane_bridge` | 暂时无效 | 当前 controller/UTC 的 `movement_ref` 还没有可靠连接到 CAD lane label。 |
| `cad_signal_arrow_direction_match` | 当前无有效样例 | 没找到可用的 left/right/ahead direction-only movement match。保留为 fallback。 |
| `semantic_movement_lane_proxy` | 当前未使用 | 当前 CAD geometry 已经能生成真实 lane candidates，不需要 synthetic movement lane。 |
| `pdf_same_page_assignment` | 对 337L / 950L 暂时无效 | PDF facts 在 `pdf_page` 坐标中，而当前 active lane source 是 CAD lane，不是 PDF lane。 |
| `pdf_to_cad_transform_required` | 被坐标转换阻塞 | PDF facts 不能直接落到 CAD lanes。需要 PDF-to-CAD affine / homography transform。 |
| `gis_to_cad_transform_required` | 当前不需要 | 当前测试输出里没有需要落到 CAD lane 的 GIS facts。 |

## 337L 结果

### `cad_context_validation`

结果：

- status: `effective`
- matched: `11`
- candidates: `15`

实际示例：

```json
{
  "lane_ref": "lane_1",
  "source_file": "local_data/Leeds City Council cite data/337L/UTC_716709_AJB_2a.dwg",
  "source_fact_name": "lane_geometry_candidate_from_cad",
  "lane_validation_status": "cad_context_confirmed",
  "requires_context_match": false,
  "validation_evidence_groups": ["arrow", "cad_block", "pole", "road_marking", "signal_head"],
  "validation_evidence_counts": {
    "arrow": 1,
    "cad_block": 41,
    "pole": 33,
    "road_marking": 3,
    "signal_head": 20
  }
}
```

解释：

这条 lane 是 CAD heuristic lane，但它周围有多类 CAD context evidence，因此被确认：

- arrow
- CAD block
- pole
- road marking
- signal head

所以它可以从：

```json
"requires_context_match": true
```

降为：

```json
"requires_context_match": false
```

### `cad_movement_label_nearest_lane`

结果：

- status: `no_cad_movement_label_matches`
- matched: `0`
- candidates: `4`

原因：

候选文字更像 CAD key / notes / legend，而不是真实 lane movement label。例如说明 pole offset、signal pole notes 等。这些文字虽然包含 `STRAIGHT` 等 movement-like token，但不是车道上的 movement 标注。

因此现在规则会阻止 key / legend / note / dim / title 图层上的 CAD movement label 自动落 lane。

### `pdf_to_cad_transform_required`

结果：

- status: `blocked_without_transform`
- candidates: `1703`

实际示例：

```json
{
  "fact_name": "road_marking_candidate_from_pdf_cv",
  "source_file": "local_data/Leeds City Council cite data/337L/337L RODLEY RBOUT SPEC 15_6_15.pdf",
  "evidence_location": "local_data/Leeds City Council cite data/337L/337L RODLEY RBOUT SPEC 15_6_15.pdf -> page 1 image cv line 1",
  "lane_ref": null,
  "intersection_ref": "intersection_1",
  "coordinate_space": "pdf_page",
  "page_ref": "local_data/Leeds City Council cite data/337L/337L RODLEY RBOUT SPEC 15_6_15.pdf#page=1",
  "assignment_method": "intersection_only",
  "reason": "pdf_page_without_cad_transform"
}
```

解释：

这个 fact 来自 PDF image/CV，坐标空间是 `pdf_page`。当前 CAD lane 在 `cad_modelspace`，两个坐标系不能直接比较。所以它只能停留在 intersection 层级，除非后续实现 PDF-to-CAD transform。

## 950L 结果

### `cad_context_validation`

结果：

- status: `effective`
- matched: `5`
- candidates: `12`

实际示例：

```json
{
  "lane_ref": "lane_2",
  "source_file": "local_data/Leeds City Council cite data/950L/UTC-950L A63 Selby Rd Ninelands La EDIT.dwg",
  "source_fact_name": "lane_geometry_candidate_from_cad",
  "lane_validation_status": "cad_context_confirmed",
  "requires_context_match": false,
  "validation_evidence_groups": ["cad_block", "pole", "signal_geometry", "signal_head"],
  "validation_evidence_counts": {
    "cad_block": 13,
    "pole": 10,
    "signal_geometry": 10,
    "signal_head": 9
  }
}
```

解释：

这条 lane 被多类 CAD context evidence 支持：

- CAD block
- pole
- signal geometry
- signal head

因此可以确认。

### `cad_movement_label_nearest_lane`

结果：

- status: `no_cad_movement_label_matches`
- matched: `0`
- candidates: `2`

原因：

候选文本包括类似：

- `AHEAD ONLY`
- `LEFT TURN ONLY`

但它们来自 `UTC_KEY` 图层。`UTC_KEY` 很可能是图例/说明，而不是道路空间中的真实 lane label。因此当前规则不会自动把它们落到 lane。

这一步是必要的，否则会把图例里的 movement text 错误连接到某条 lane。

### `pdf_to_cad_transform_required`

结果：

- status: `blocked_without_transform`
- candidates: `555`

实际示例：

```json
{
  "fact_name": "road_marking_candidate_from_pdf_cv",
  "source_file": "local_data/Leeds City Council cite data/950L/950L CH 16-05-24.pdf",
  "evidence_location": "local_data/Leeds City Council cite data/950L/950L CH 16-05-24.pdf -> page 1 image cv line 1",
  "lane_ref": null,
  "intersection_ref": "intersection_1",
  "coordinate_space": "pdf_page",
  "page_ref": "local_data/Leeds City Council cite data/950L/950L CH 16-05-24.pdf#page=1",
  "assignment_method": "intersection_only",
  "reason": "pdf_page_without_cad_transform"
}
```

解释：

和 337L 一样，PDF facts 现在不能直接落到 CAD lanes，因为没有 PDF-to-CAD transform。

## 筛选决定

当前主方法应该是：

```text
cad_context_validation
```

原因：

- 它只在同一个坐标空间 `cad_modelspace` 内工作。
- 它要求至少两类独立 CAD evidence，而不是只靠 nearest distance。
- 它能输出 `validation_evidence_groups` 和 `validation_evidence_counts`，方便人工审核。
- 它不会把 PDF page 坐标或 GIS 坐标强行匹配到 CAD lane。

暂时不作为主方法的原因：

| 方法 | 原因 |
| --- | --- |
| `cad_movement_label_nearest_lane` | 当前真实数据中的 candidate 多来自 key/legend/notes，风险高。 |
| `semantic_movement_to_cad_lane_bridge` | 需要 controller/UTC movement 和 CAD label 共享可靠 `movement_ref`，目前数据还不够。 |
| `pdf_to_cad_transform_required` | 需要先实现 PDF-to-CAD transform，否则坐标不可比。 |

## 下一步建议

1. 继续增强 CAD parser，让更多 signal head、pole、arrow、road marking、stop line、真实 road/lane text 被识别成结构化 facts。
2. 使用 `nearest_validation_candidates[]` 检查未确认 lanes，判断是否需要补 CAD layer / block / text 规则。
3. 对 PDF facts，下一步不是直接 nearest CAD lane，而是先做 PDF-to-CAD transform。
4. 对 semantic movement，下一步是提高 `phase -> movement_ref` 和 `CAD label -> movement_ref` 的一致性。

## 当前状态总结

| Site | CAD heuristic lanes | Confirmed by CAD context | Still needs context match | 主要阻塞 |
| --- | ---: | ---: | ---: | --- |
| `337L` | 15 | 11 | 4 | 少数 lane 缺少足够独立 CAD context；PDF facts 缺少 PDF-to-CAD transform |
| `950L` | 12 | 5 | 7 | 多条 lane 只有单类 evidence 或 evidence 被分配到其他 lane；PDF facts 缺少 PDF-to-CAD transform |

结论：

`cad_context_validation` 是目前最有效、最安全的 lane 确认方法。其他方法应保留为辅助诊断或未来增强方向，不应在当前阶段强行作为主匹配逻辑。
