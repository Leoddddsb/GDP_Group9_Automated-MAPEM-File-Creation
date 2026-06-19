# Project Plan（本地中文版）

本文档用于规划自动生成 MAPEM 文件的整体方法。当前项目不再只基于 Leeds PDF + DWG 数据，而是扩展到更广泛的输入文件和数据来源，包括 PDF、DOCX、DWG/DXF、ZIP、TXT/8TX、GIS/OSM，以及未来可能出现的 survey / LiDAR 数据。

新的核心思路是：先确认 MAPEM 需要哪些元素，然后按文件格式使用可实现的 parser 抽取 MAPEM 相关 facts，再把这些 facts 直接匹配到 MAPEM fields，形成 field-source matrix，最后通过多来源 evidence fusion 生成 `SiteModel`。

这里要避免两个极端：

- 不按“PDF/CAD”直接生成 MAPEM，因为同一个 PDF 可能抽出不同类型的 facts。
- 不额外判断文件属于哪一种来源类别，因为这对提取 MAPEM 所需字段帮助有限，且会增加不必要复杂度。

因此第一版采用更稳的工程流程：**file-format extraction first, MAPEM field matching second**。

## 1. 建议的探索顺序

整体关系：

| Step | 本步做什么 | 产出文件 | 对应 GitHub 文件夹 |
| --- | --- | --- | --- |
| Step 1 | 建立 file inventory，记录每个 site 有哪些输入文件 | `site_inventory.partial.json` | `configs/`, `src/mapemgen/ingestion/` |
| Step 2 | 按文件格式抽取 MAPEM 相关 facts | `extracted_facts.partial.json` | `src/mapemgen/ingestion/` |
| Step 3 | 将 extracted facts 匹配到 MAPEM fields，并生成 field-source matrix | `mapped_evidence.partial.json`, `field_source_matrix.md` | `src/mapemgen/`, `docs/` |
| Step 4 | 合并多来源 mapped evidence，自动转换为 MAPEM-style SiteModel 和 MAPEM 输出 | `site_model.json`, `mapem.json`, `mapem.asn1` | `src/mapemgen/`, `src/mapemgen/generators/`, `schemas/` |
| Step 5 | 自动验证并输出低置信度和需人工处理项 | `validation_report.json` | `src/mapemgen/validation/` |
| Step 6 | 用 training / validation site split 做 robustness 测试 | `robustness_summary.json` | `tests/`, `docs/` |
| Step 7 | 计算转换质量评分 | `validation_report.json` | `src/mapemgen/validation/`, `docs/` |

说明：这里的“对应 GitHub 文件夹”指后续实现该步骤时，代码、配置或文档主要应该放在哪些仓库文件夹中；它不是输出文件的保存位置。

### Step 1: 建立 file inventory

程序以一个 site 文件夹路径作为输入，自动生成一个本地 `site_inventory.partial.json`。这一步是 folder-level file inventory，不是 MAPEM facts extraction。它只记录这个文件夹里有哪些输入文件、总共有多少个文件、文件格式分别是什么、文件名线索、基础可读性状态，以及每个文件建议交给哪个 parser。

```text
site_id
site_name
local_authority_or_dataset
input_folder_path
inventory_summary:
  - total_files
  - file_type_counts
  - readable_files
  - unreadable_files
source_files:
  - file_path
  - file_type
  - file_size_bytes
  - filename_hints
  - readable_status
  - parser_to_use
  - notes
```

```text
PDF       -> pdf text/table/drawing parser
DOCX      -> docx text/table parser
DWG/DXF   -> CAD geometry parser
ZIP       -> package inventory parser, then root DWG / xref handling
TXT/8TX   -> RAM / text parser
MOVA      -> binary/proprietary file; first version only records availability
GIS/OSM   -> GIS/public data parser
LiDAR     -> survey/point-cloud parser, if data is available
```

文件名关键词也会被自动记录为 `filename_hints`，用于提示后续可能包含的信息：

| 文件名关键词 | 自动生成的 hint | 可能用途 |
| --- | --- | --- |
| `Spec`, `2500Config`, `Configuration` | possible configuration file | 可能包含 phases、stages、streams、controller settings |
| `Drawing`, `AsBuilt`, `DetailedDesign` | possible drawing / layout file | 可能包含 road layout、crossings、detectors、stage diagram |
| `UTCForm` | possible UTC form | 可能包含 SCN、site metadata、SCOOT links、staging |
| `SCOOTDets` | possible SCOOT detector data | 可能包含 detector IDs、approach links |
| `RAMData` | possible RAM / override data | 可能包含 timing changes、intergreen overrides、detector overrides |
| `MOVA` | possible MOVA/control logic data | 可能包含 MOVA detector/control information |
| `.zip` containing `.dwg` | possible CAD package | 可能包含 root drawing、xref、OS/topographic drawing |

例如程序可以自动生成：

```json
{
  "site_id": "1003",
  "site_name": "London Rd Cleveland Bridge",
  "local_authority_or_dataset": "DCIS/Bathnes",
  "input_folder_path": "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge",
  "inventory_summary": {
    "total_files": 3,
    "file_type_counts": {
      "txt": 1,
      "zip": 1,
      "8tx": 1
    },
    "readable_files": 3,
    "unreadable_files": 0
  },
  "source_files": [
    {
      "file_path": "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge/T1003 Cleveland Place.txt",
      "file_type": "txt",
      "file_size_bytes": 12345,
      "filename_hints": ["possible site notes", "possible controller or RAM text"],
      "readable_status": "text_readable",
      "parser_to_use": "ram_text_parser",
      "notes": ""
    },
    {
      "file_path": "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge/T1003 Cleveland Place - Standard.zip",
      "file_type": "zip",
      "file_size_bytes": 67890,
      "filename_hints": ["possible CAD package", "possible standard controller export package"],
      "readable_status": "archive_readable",
      "parser_to_use": "zip_inventory_parser",
      "notes": "Step 1 可以检查压缩包成员，但不在这一步抽取 MAPEM facts。"
    }
  ]
}
```

产出文件：`site_inventory.partial.json`  
对应 GitHub 文件夹：`configs/`, `src/mapemgen/ingestion/`  
说明：`configs/` 放 site 配置和 parser 规则，`src/mapemgen/ingestion/` 放自动读取文件并生成 file inventory 的代码。

### Step 2: 按文件格式抽取 MAPEM 相关 facts

这一步按文件格式使用 extractor，把每个文件中与 MAPEM 相关的信息抽成中间 facts。这里不是 extract everything，而是 extract everything relevant to MAPEM。

整体关系：

```text
input files
        |
        +-- PDF extractor
        +-- DOCX extractor
        +-- CAD/DXF extractor
        +-- ZIP inventory extractor
        +-- TXT/8TX RAM extractor
        +-- GIS/OSM extractor
        |
        +-- extracted_facts.partial.json
```

不同 parser 的第一版职责：

| Parser | 输入 | 输出 fact types |
| --- | --- | --- |
| PDF parser | spec PDF, drawing PDF, config PDF, MOVA report PDF | page text, tables, phase/stage tables, drawing labels, stage diagrams, detector labels |
| DOCX parser | UTC form, RAM record, MOVA drawing notes | site metadata, SCN, IP, staging, SCOOT links, timing data, RAM notes |
| CAD/DXF parser | DWG converted DXF, root drawing, xrefs | lane candidates, stop line candidates, crossing candidates, signal head candidates, layer names, coordinate range |
| ZIP parser | DWG packages | root drawing, xref list, OS/topographic drawing availability |
| TXT/8TX parser | RAM differences report | changed timings, intergreen overrides, detector overrides, I/O allocation differences |
| GIS/OSM parser | public GIS / OSM | road names, approximate topology, speed limits, approximate refPoint |
| LiDAR/survey parser | survey/LiDAR data if available | kerbs, lane edges, high resolution topographic evidence |

`extracted_facts.partial.json` 示例：

```json
{
  "site_id": "1003",
  "source_file": "1003_UTCForm_May24.docx",
  "file_type": "docx",
  "extracted_facts": [
    {
      "fact_type": "site_name",
      "value": "1003 A4 London Rd / Cleveland Place",
      "evidence_location": "UTC Junction Description",
      "confidence": 0.95
    },
    {
      "fact_type": "scoot_link",
      "value": "N04211A London Rd WB Ahead",
      "evidence_location": "SCOOT Links table",
      "confidence": 0.90
    }
  ]
}
```

产出文件：`extracted_facts.partial.json`  
对应 GitHub 文件夹：`src/mapemgen/ingestion/`

### Step 3: MAPEM field matching 和 field-source matrix

这一步把 Step 2 抽出来的 facts 匹配到 MAPEM fields。`field-source matrix` 不是一开始凭空假设出来的，而是基于真实 extracted facts 自动生成或半自动整理出来的报告。

处理关系：

```text
extracted_facts.partial.json
        |
        +-- fact_type to MAPEM field matching rules
        |
        +-- mapped_evidence.partial.json
        |
        +-- field_source_matrix.md
```

示例匹配规则：

| fact_type | 可以匹配到的 MAPEM field | 说明 |
| --- | --- | --- |
| `site_name` | `IntersectionGeometry.name` | site 名称或 junction description |
| `junction_centre_candidate` | `IntersectionGeometry.refPoint` | CAD/GIS/drawing 中推断的路口参考点 |
| `lane_candidate` | `GenericLane.nodeList` | 需要后续转换成 MAPEM `NodeXY` |
| `stop_line_candidate` | lane start/end and approach assignment | 辅助判断 lane direction 和 ingress/egress |
| `phase_label` | `connectsTo.signalGroup` candidate | phase label 需要和 movement / lane connection 匹配 |
| `stage_phase_table` | `connectsTo.signalGroup`, `maneuvers` | 提供 phase/stage/movement 关系 |
| `scoot_link` | lane / approach semantic evidence | 辅助判断 approach 和 movement |
| `ram_intergreen_override` | validation evidence for timing/control | 主要用于 validation 或 override |

生成的 `field_source_matrix.md` 示例：

| MAPEM field | matched facts | source files | evidence location | confidence |
| --- | --- | --- | --- | ---: |
| `IntersectionGeometry.refPoint` | `junction_centre_candidate`, `gis_intersection_point` | CAD/DXF, OSM | CAD coordinates, OSM node | 0.82 |
| `GenericLane.nodeList` | `lane_candidate` | CAD/DXF | CAD layer / polyline | 0.78 |
| `connectsTo.signalGroup` | `phase_label`, `stage_phase_table` | config PDF, UTC form DOCX | PDF table, DOCX section | 0.86 |
| `signalHeadLocations` | `signal_head_candidate`, `pole_candidate` | CAD/DXF, asset data | CAD symbol / asset record | 0.74 |

工程上这一步要做两件事：

1. 让程序知道哪些 facts 可以进入哪个 MAPEM 字段。
2. 让报告清楚说明每个 MAPEM 字段来自哪些文件、哪些 facts、哪些 evidence location，以及可信度如何。

`mapped_evidence.partial.json` 示例：

```json
{
  "site_id": "1003",
  "mapem_field": "IntersectionGeometry.refPoint",
  "matched_fact_type": "junction_centre_candidate",
  "value": "...",
  "source_file": "T1003 Cleveland Place.dwg",
  "file_type": "dwg",
  "evidence_location": "CAD layer / coordinates",
  "confidence": 0.82
}
```

产出文件：`mapped_evidence.partial.json`, `field_source_matrix.md`  
对应 GitHub 文件夹：`src/mapemgen/`, `docs/`

### Step 4: 多来源 evidence fusion，并自动转换为 MAPEM-style SiteModel

这一步把 Step 3 产生的 mapped evidence 合并成内部 `SiteModel`。重点不是简单拼接，而是处理多来源互补、冲突和置信度。

具体处理方式：

```text
mapped_evidence.partial.json
        |
        +-- 按 site_id 分组
        |
        +-- 按 mapem_field 分组
        |
        +-- 对每个 MAPEM 字段收集 candidate values
        |
        +-- 根据 source priority + confidence + consistency 选择 final value
        |
        +-- 写入 SiteModel 对应字段
        |
        +-- 无法自动确定的字段写入 manual_review_items
```

也就是说，Step 2 的输出是 raw facts，Step 3 把 raw facts 变成 mapped evidence，Step 4 才负责把 mapped evidence 变成 `SiteModel` 的最终字段。

处理规则可以先设计成：

| 处理情况 | 程序怎么做 | SiteModel 结果 |
| --- | --- | --- |
| 只有一个高置信度 evidence | 直接采用 | 写入对应字段 |
| 多个 evidence 一致 | 采用 preferred source 或最高 confidence 的值 | 写入对应字段，并保留 provenance |
| 多个 evidence 接近但不完全一致 | 选择最高置信度值，同时降低字段 confidence | 写入字段，并生成 warning |
| 多个 evidence 明显冲突 | 不自动决定，生成 `manual_review_item` | 字段可暂时为空或使用低置信度候选值 |
| 缺少 evidence | 标记 missing field | 字段为空，并进入 validation report |

示例：形成 `refPoint` 字段。

```json
[
  {
    "mapem_field": "IntersectionGeometry.refPoint",
    "value": { "lat": 53.8123, "lon": -1.5762 },
    "source_file": "T1003 Cleveland Place.dwg",
    "confidence": 0.85
  },
  {
    "mapem_field": "IntersectionGeometry.refPoint",
    "value": { "lat": 53.8121, "lon": -1.5760 },
    "source_file": "OpenStreetMap",
    "confidence": 0.70
  }
]
```

如果两个候选点距离很近，程序可以采用 CAD 的值，因为 CAD 是 `refPoint` 的 preferred source，并且 confidence 更高。写入后的 `SiteModel` 是：

```json
{
  "mapData": {
    "intersections": [
      {
        "refPoint": {
          "lat": 53.8123,
          "lon": -1.5762
        }
      }
    ]
  }
}
```

同时 SiteModel 内部可以保留 provenance 和 confidence，用于后续 validation：

```json
{
  "field": "IntersectionGeometry.refPoint",
  "selected_source": "T1003 Cleveland Place.dwg",
  "confidence": 0.85,
  "alternative_sources": ["OpenStreetMap"]
}
```

如果 CAD 和 GIS 给出的 `refPoint` 差距过大，程序不应该直接写死一个结果，而是生成 `manual_review_item`，让用户在 review interface 中选择 `accept` 或 `correct`。人工确认后，程序再把最终值回填到 `SiteModel`。

自动转换逻辑：

```text
geometry facts
        |
        +-- mapped geometry evidence
            laneSet / nodeList / stop lines / crossings / signalHeadLocations

control facts
        |
        +-- mapped control evidence
            phases / stages / streams / signalGroup / intergreens

location and road facts
        |
        +-- mapped location and road evidence
            refPoint / road names / speedLimits / approximate topology

asset / survey facts
        |
        +-- mapped asset / survey evidence
            poles / signal heads / detector positions

evidence fusion
        |
        +-- SiteModel
        |
        +-- mapem.json
        |
        +-- mapem.asn1
```

产出文件：`site_model.json`, `mapem.json`, `mapem.asn1`  
说明：这一步产出的是第一版自动转换结果，还没有经过 Step 5 的低置信度检查和人工回填。  
`site_model.json` 是第一版中间模型；`mapem.json` 和 `mapem.asn1` 是基于这个第一版 `site_model.json` 生成的初稿。人工处理后，需要重新生成更新后的 MAPEM 输出。

`site_model.json` 到 `mapem.json` / `mapem.asn1` 的转换关系：

```text
site_model.json
        |
        +-- read as SiteModel
        |
        +-- generator filters / normalises / encodes MAPEM fields
        |
        +-- mapem.json
        |
        +-- mapem.asn1
```

当前 `SiteModel` 已经设计得接近 MAPEM 层级，所以第一版转换可能看起来像直接导出。  
但概念上仍然要分开：`site_model.json` 是项目内部中间模型，`mapem.json` 是从它筛选、规范化、编码后的 MAPEM 输出。

后续 generator 需要负责：

- 去掉内部调试字段。
- 转换字段命名。
- 检查 MAPEM 必需字段。
- 把 geometry 转成 MAPEM 需要的 `NodeXY` 表达。
- 把 lane connection 转成 MAPEM `connectsTo`。
- 把 `signalGroup` 放到正确层级。
- 生成 ASN.1-style 或标准 ASN.1 输出。

对应 GitHub 文件夹：`src/mapemgen/`, `src/mapemgen/generators/`, `schemas/`

### Step 5: 自动输出低置信度和需人工处理项

`validation_report.json` 在这一步输出。  
它读取前面各步骤的中间结果和 Step 4 生成的 `site_model.json` / `SiteModel`，检查 file inventory、fact extraction、field matching、evidence fusion 和 SiteModel 本身是否有问题。

检查对象：

```text
site_inventory.partial.json
        |
        +-- file readability / parser availability

extracted_facts.partial.json
        |
        +-- fact extraction success / missing facts

mapped_evidence.partial.json
        |
        +-- field matching success / unmatched facts

field_source_matrix.md
        |
        +-- missing MAPEM fields / weak evidence coverage

site_model.json
        |
        +-- completeness / geometry consistency / semantic consistency
```

产出文件：`validation_report.json`  
对应 GitHub 文件夹：`src/mapemgen/validation/`

`validation_report.json` 是一个结构化 JSON 报告，大概包含：

```json
{
  "site_id": "397L",
  "status": "needs_review",
  "summary": {
    "error_count": 0,
    "warning_count": 3,
    "manual_review_count": 2
  },
  "scores": {
    "file_readability_score": 95,
    "fact_extraction_score": 86,
    "field_matching_score": 82,
    "fusion_consistency_score": 80,
    "sitemodel_completeness_score": 88,
    "geometry_score": 76,
    "semantic_score": 82,
    "manual_effort_score": 84,
    "overall_quality_score": 84
  },
  "errors": [],
  "warnings": [
    "DWG georeference is missing",
    "Lane direction confidence is low"
  ],
  "manual_review_items": []
}
```

其中 `manual_review_items` 是 `validation_report.json` 里的一个列表，用来放所有低置信度、抽取失败、冲突或需要人工确认的问题项。

建议每个 site 自动输出：

```text
manual_review_items
|
+-- review_id
+-- item_id
+-- severity
+-- mapem_field
+-- issue_type
+-- current_value
+-- candidate_values
+-- evidence_source
+-- evidence_location
+-- confidence
+-- suggested_action
+-- affects_quality_score
```

这些内容应该进入 `validation_report.json`，并直接用于后续 `manual_effort_score`。

| 需要标注的低置信度 / 人工处理项 | 影响的 MAPEM 字段 | 自动检测方式 | 输出给人工的内容 | 对 `manual_effort_score` 的影响 |
| --- | --- | --- | --- | --- |
| phase / stage / control facts 抽取失败 | `connectsTo.signalGroup`, `maneuvers`, stage/phase metadata | 找不到 phase/stage/stream 信息、表格行数异常、phase labels 缺失 | 文件名、页码/section、失败表名、原始文本片段 | 高 |
| phase / stage / control facts 内部冲突 | `signalGroup`, `maneuvers` | stage table 中出现 phase，但 phase list 没有定义，或不同文件给出不同结果 | 冲突的 phase label、对应 evidence | 高 |
| geometry facts 证据不足 | `GenericLane.nodeList`, `connectsTo`, `signalHeadLocations` | PDF / CAD / survey 中无法稳定识别 lane、stop line、crossing 或 signal head | 文件名、CAD layer、PDF 图纸区域、候选对象 | 高 |
| 文件无法读取或 parser 不可用 | depends on file | 文件损坏、PDF 无法提取、DWG 未转换、ZIP 缺少 root drawing | 文件名、file_type、失败原因、建议 parser | 中高 |
| fact 无法匹配到 MAPEM field | affected MAPEM field | extracted fact 存在，但没有 matching rule 或匹配结果为空 | fact_type、source file、建议匹配字段 | 中 |
| field-source matrix 显示字段无来源 | affected MAPEM field | 某个 required MAPEM field 没有任何 matched evidence | 缺失 MAPEM field、已尝试文件、影响范围 | 高 |
| fusion 无法自动决定最终值 | affected MAPEM field | 多个 candidate values 合法但无法根据规则选择 | candidate values、来源文件、建议人工选择 | 高 |
| SiteModel 引用错误 | lane references, `connectsTo`, `signalGroup` | `connectsTo` 指向不存在的 lane，或 `signalGroup` 引用缺失 | 错误字段、引用 ID、相关 evidence | 高 |
| 多来源 evidence 冲突 | affected MAPEM field | CAD、drawing PDF、GIS、asset data 给出互相冲突的位置或属性 | 冲突文件、candidate values、confidence | 中高 |
| 某个 MAPEM 字段没有匹配到足够 facts | affected MAPEM field | 该字段没有可用 extracted facts，或只有低置信度 facts | 缺失字段、尝试过的文件、受影响字段 | 中高 |
| 坐标系不明 | `refPoint`, `nodeList.nodes`, `signalHeadLocations` | DWG/DXF 缺少可识别 georeference，或坐标范围不像 WGS84 / local grid | CAD 文件名、坐标范围、无法识别的 CRS 证据 | 高 |
| DWG 没有 georeference | `refPoint`, all geometry offsets | 无 EPSG / world file / known control point；无法把 CAD 坐标转换为 lat/lon | 需要人工选择 refPoint 或提供 control points | 高 |
| CAD symbol layer 不一致或识别不到 | `signalHeadLocations`, signal head to `signalGroup` mapping | layer rules 没有匹配到 signal head / pole symbols，或同类 symbol 出现在多个未知 layer | 未匹配 layer names、symbol count、候选对象截图/坐标 | 中高 |
| lane centreline 断裂或太短 | `GenericLane.nodeList.nodes` | polyline 长度过短、节点少于阈值、断点距离过大 | lane candidate ID、坐标、所在 CAD layer | 高 |
| lane 方向不确定 | `ingressApproach`, `egressApproach`, `connectsTo` | polyline 方向与 approach/stop line/movement 推断冲突 | 候选方向、相关 road label、stop line 位置 | 中高 |
| `connectsTo` 有多个候选出口 | `GenericLane.connectsTo` | 一个 ingress lane 几何上匹配多个 downstream lanes，分数接近 | source lane、候选 target lanes、各自 confidence | 高 |
| movement 推断不确定 | `maneuvers`, `connectsTo.connectingLane.maneuver` | 几何角度与 PDF stage arrow/phase description 不一致 | left/straight/right 候选、角度、PDF 证据 | 高 |
| `signalGroup` 找不到对应 lane movement | `connectsTo.signalGroup` | phase label 有定义，但无法匹配到 lane connection | phase label、PDF location、候选 lanes | 高 |
| `signalGroup` 被多个冲突 movement 共用 | `connectsTo.signalGroup`, consistency checks | conflict matrix 显示冲突，但 mapping 后共用同一 movement group | 冲突 phase、affected lanes、conflict table 位置 | 高 |
| stop line 无法识别 | lane start/end, approach assignment | CAD layer rules 找不到 stop line，或 stop line 与 lane 端点距离过大 | candidate lane、最近 stop line 距离、layer evidence | 中 |
| pedestrian crossing geometry 缺失 | pedestrian lanes / crossings, `signalHeadLocations` | 已抽取到 pedestrian / puffin phase，但 PDF/CAD 中找不到 crossing geometry | phase label、相关 evidence、geometry missing evidence | 中 |
| roundabout internal lanes 无法稳定连接 | `laneSet`, `connectsTo` | 多 stream roundabout 中 internal lanes 与 entry/exit lanes 匹配不唯一 | affected stream、candidate lanes、matching score | 高 |
| speed limit 缺失 | `speedLimits` | PDF/GIS/OSM 均未找到 speed limit | site ID、缺失字段 | 低 |
| restrictions 缺失 | `restrictionList` | PDF notes/CAD markings 未解析到 restrictions | site ID、缺失字段 | 低到中 |

`manual_review_items` 的示例输出：

```json
{
  "manual_review_items": [
    {
      "review_id": "R1",
      "item_id": "397L-CAD-001",
      "severity": "high",
      "mapem_field": "IntersectionGeometry.refPoint",
      "issue_type": "dwg_georeference_missing",
      "current_value": null,
      "candidate_values": [
        { "lat": 53.8123, "lon": -1.5762, "source": "estimated junction centre" }
      ],
      "evidence_source": "DWG/DXF",
      "evidence_location": "UTMC_300097_397L_04.dwg",
      "confidence": 0.30,
      "suggested_action": "Accept the estimated refPoint or select a corrected reference point in the review interface.",
      "affects_quality_score": ["geometry_score", "manual_effort_score"]
    }
  ]
}
```

每个 `manual_review_item` 应该让客户一眼看出：

- 界面里需要处理的短 ID，例如 `R1`。
- 哪个 MAPEM 字段需要确认，例如 `connectsTo.signalGroup`。
- 当前系统填了什么值，例如 `current_value`。
- 系统认为可能的候选值是什么，例如 `candidate_values`。
- 不确定性来自哪里，例如 PDF 页码、CAD layer、DXF 坐标。
- 客户需要做什么，例如 `accept` 或 `correct`。

`manual_effort_score` 可以按这些 items 自动计算：

```text
manual_effort_score = 100 - weighted_manual_review_cost

weighted_manual_review_cost =
  high_severity_count * 8
+ medium_severity_count * 4
+ low_severity_count * 1
+ manual_override_count * 3
```

人工回填方式建议使用界面直接回填到 `SiteModel`，不要求客户在终端中手动编辑 JSON。

流程如下：

```text
1. 自动转换
   mapped evidence -> SiteModel -> mapem.json / mapem.asn1

2. 自动验证
   生成 validation_report.json
   里面列出 manual_review_items

3. 客户在界面中 review
   每一项显示：
   - 问题是什么
   - 影响哪个 MAPEM 字段
   - 系统建议值
   - confidence
   - source file / PDF 页码 / DOCX section / CAD layer / GIS feature / 坐标证据

4. 客户选择操作
   - Accept：接受系统结果
   - Correct：输入或选择修正值

5. 系统自动回填
   - 更新 SiteModel
   - 更新 validation_report.json
   - 重新计算 quality score
   - 重新生成 mapem.json / mapem.asn1
```

这种设计下，客户面对的是 review interface，而不是终端。

人工操作只需要两种。客户在界面中按 `review_id` 操作：

| 人工操作 | 意思 | 需要填写 |
| --- | --- | --- |
| `accept` | 自动结果是对的 | 不需要额外填写 |
| `correct` | 自动结果错了，人工修正 | 只填写新的 `candidate_values` |

我们会设计一个 review interface 给客户使用。  
界面会把 `manual_review_items` 汇总展示出来，而不是让客户直接看 JSON。客户可以看到每个 `review_id` 对应的问题、影响的 MAPEM 字段、系统候选值、confidence、PDF/CAD 证据和建议操作。

客户在界面中选择 `accept` 或 `correct`。  
如果选择 `correct`，界面只要求客户填写新的候选值；程序负责把这个反馈转换成内部数据更新。

客户点击 `Accept` / `Correct` 后，程序用该 `review_id` 找到对应的 `mapem_field`，再直接更新内部 `SiteModel`：

```json
{
  "mapData": {
    "intersections": [
      {
        "refPoint": {
          "lat": 53.8123,
          "lon": -1.5762
        }
      }
    ]
  }
}
```

同时在 `validation_report.json` 里记录处理状态：

```json
{
  "review_id": "R1",
  "item_id": "397L-CAD-001",
  "resolution": {
    "status": "corrected",
    "candidate_values": [
      { "lat": 53.8123, "lon": -1.5762, "source": "manual correction from review interface" }
    ]
  }
}
```

完成回填后，系统重新计算 quality score，并重新生成 `mapem.json` / `mapem.asn1`。

### Step 6: 用 training / validation site split 做 robustness 测试

在自动提取并输出 `manual_review_items` 后，再做 robustness 测试。
现在的 robustness 不应该只看 6 个 Leeds sites，而是要覆盖不同文件组合、不同可用字段和不同几何复杂度：Leeds 的 PDF spec + DWG、DCIS/Bathnes 的 config PDF + UTC form DOCX + drawing PDF + DWG zip + RAM/MOVA、以及未来可能加入的 GIS / asset / survey / LiDAR。

产出文件：`robustness_summary.json`  
对应 GitHub 文件夹：`tests/`, `docs/`

建议把数据分成两类：

| 数据用途 | 作用 | 示例 |
| --- | --- | --- |
| Modelling / development subset | 用来探索 parser、field matching rules、调试 evidence fusion | Leeds 的一部分 + DCIS/Bathnes 的一部分 |
| Held-out validation subset | 不参与规则开发，只用于验证 generality 和 robustness | 剩余典型 sites |

选择 development subset 时，要覆盖不同数据源组合：

| 组合类型 | 代表性数据 | 为什么需要 |
| --- | --- | --- |
| signal spec PDF + DWG | Leeds sites | 验证最基础的 specification + CAD pipeline |
| config PDF + UTC form DOCX + drawing PDF + DWG zip | DCIS/Bathnes sites | 验证多文件、多格式、多来源 facts 的融合 |
| pedestrian / Toucan / Puffin crossing | 397L, 378L, 1084, 5062 | 验证较简单但有 pedestrian phases 的场景 |
| bus gate / shuttle | 1013 | 验证 restriction、special movement 和 non-standard layout |
| multi-stream junction | 1062, 950L | 验证 streams、stages、signalGroup 映射 |
| roundabout | 573L, 337L | 验证复杂 `connectsTo` 和 internal lanes |
| MOVA / SCOOT rich site | 1003, 5040, 1084 | 验证 control logic 和 detector evidence 的利用 |

Leeds 数据仍然可以按复杂度作为一条 baseline：

1. `397L`：最简单，Toucan，1 stream，2 stages。
2. `378L`：Toucan，但 PDF 模板和 MOVA 信息更多。
3. `982L`：3-way junction，8 phases，puffin + all-red demand。
4. `950L`：MOVA/VA，puffin upgrade，dummy phases，hurry call。
5. `573L`：roundabout，5 streams。
6. `337L`：最大 roundabout，8 streams，24 stages。

新增 DCIS/Bathnes 数据用于扩展文件组合覆盖：

1. `1084`：Puffin pedestrian crossing，含 config PDF、UTC form、drawing PDF、MOVA Tools Report、DWG zip。
2. `5062`：pedestrian crossing，含 PTC-1 config、UTC form、as-built drawing、MOVA drawing、MOVA file、DWG zip。
3. `1013`：Bus Gate / Shuttle，含 config PDF、UTC form、as-built drawing、RAM data、DWG zip。
4. `1003`：London Rd / Cleveland Place，含 SCOOT、config PDF、UTC form、drawing、DWG xrefs。
5. `1062`：London Rd / Morrisons，多 stream，含 SCOOT detectors、config PDF、UTC form、DWG zip。
6. `5040`：A37 / A39 White Cross，含 MOVA drawing、MOVA file、UTC form、config PDF、DWG zip。

这个设计可以帮助衡量：

- 不同文件格式下，MAPEM 相关 facts extraction 是否稳定。
- 同一文件格式但不同语义内容时，field matching 是否准确。
- 不同 DWG layer style 和 xref 结构下，CAD geometry extractor 是否稳定。
- stream / stage / phase 数量增加时，`connectsTo.signalGroup` 映射是否还能保持清楚。
- roundabout 这种复杂几何是否需要额外人工规则。
- 多来源 evidence 冲突时，fusion layer 是否能给出正确 confidence 和 manual review item。
- `manual_review_items` 的数量和严重程度是否会随复杂度显著增加。

Robustness 不只看一个 site 的分数，而是看不同数据源组合和不同 site 类型上是否稳定：

| Robustness 指标 | 含义 |
| --- | --- |
| site_success_rate | validation subset 中有几个 site 能生成有效 `SiteModel` |
| average_quality_score | validation subset 的平均质量分 |
| worst_site_score | 最差 site 的分数，防止平均值掩盖失败 |
| score_variance | 不同 site 分数波动，衡量稳定性 |
| field_matching_error_count | extracted facts 匹配到 MAPEM fields 的错误次数 |
| parser_failure_count | PDF/DOCX/CAD/GIS parser 失败次数 |
| evidence_conflict_count | 多来源 evidence 冲突次数 |
| manual_intervention_rate | 每个 site 平均需要多少人工修正 |
| complexity_drop | 从简单 pedestrian crossing 到 roundabout / multi-stream site 时分数下降多少 |

### Step 7: 建立转换质量评分系统

除了能不能生成 `mapem.json` / `mapem.asn1`，还需要量化转换质量。
建议每个 site 生成一个 `validation_report.json`，同时给出 0-100 的综合分数。

产出文件：`validation_report.json`  
对应 GitHub 文件夹：`src/mapemgen/validation/`, `docs/`

```text
conversion_quality_score
|
+-- file_readability_score       文件能否被读取和进入 parser
+-- fact_extraction_score        MAPEM 相关 facts 是否成功抽取
+-- field_matching_score         extracted facts 到 MAPEM fields 的匹配质量
+-- fusion_consistency_score     多来源 evidence 合并和冲突处理质量
+-- sitemodel_completeness_score SiteModel 必需字段完整度
+-- geometry_score               几何质量
+-- semantic_score               phase / movement / signalGroup 语义正确性
+-- manual_effort_score          人工修正成本
```

说明：`conversion_quality_score` 是单个 site 的 0-100 分。  
`robustness_score` 不放进单个 site 的质量分里，而是在 Step 6 的 `robustness_summary.json` 中跨多个 sites 计算。

建议权重：

| 评分项 | 权重 | 衡量什么 | 主要依据 |
| --- | ---: | --- | --- |
| File readability | 10% | 输入文件是否能被发现、读取并交给合适 parser | `site_inventory.partial.json`, parser availability, file read errors |
| Fact extraction | 15% | 是否成功抽取 MAPEM 相关 facts | `extracted_facts.partial.json`, parser failures, missing fact types |
| Field matching | 15% | extracted facts 是否被正确匹配到 MAPEM fields | `mapped_evidence.partial.json`, unmatched facts, matching rules |
| Fusion consistency | 10% | 多来源 evidence 是否正确合并，冲突是否被识别 | candidate values、confidence、manual review items |
| SiteModel completeness | 15% | MAPEM 必需字段是否填齐 | `mapData`, `intersections`, `laneSet`, `nodeList`, `connectsTo`, `signalGroup` |
| Geometry quality | 15% | 车道几何是否准确、连续、方向正确 | DXF geometry、人工抽查、与底图/原 CAD 对照 |
| Semantic quality | 10% | movement、phase、signalGroup 映射是否正确 | PDF/DOCX stage/phase facts、phase labels、人工校核 |
| Manual effort | 10% | 需要多少人工修正 | `manual_review_items` 数量、严重程度、manual overrides 数量和耗时 |

跨 site 的 robustness 单独报告，不参与上面单个 site 的 100 分权重。  
这样可以清楚地区分两个问题：一个 site 的转换质量如何，以及同一套 pipeline 在不同数据组合上是否稳定。

单个 site 的评分可以这样解释：

```text
90-100  高质量：可作为接近生产级的输出
75-89   可用：主要结构正确，但仍需要少量人工检查
60-74   部分可用：可用于研究展示，但关键字段仍需人工修正
<60     不可靠：不能说明转换成功，只能作为失败案例分析
```

最终报告建议按 site 输出：

| Site | 数据组 | 类型 | File coverage | Quality score | 主要扣分原因 | Manual effort | Robustness 观察 |
| --- | --- | --- | --- | ---: | --- | --- | --- |
| 397L | Leeds | Toucan | spec PDF + DWG | TBD | TBD | TBD | MVP baseline |
| 378L | Leeds | Toucan | spec PDF + DWG | TBD | TBD | TBD | 检查 PDF 模板差异 |
| 982L | Leeds | 3-way junction | spec PDF + DWG | TBD | TBD | TBD | 检查 puffin / all-red demand |
| 337L | Leeds | Large roundabout | spec PDF + DWG | TBD | TBD | TBD | stress test |
| 1084 | DCIS/Bathnes | Puffin crossing | config PDF + UTC form + drawing PDF + MOVA report + DWG zip | TBD | TBD | TBD | 多 source evidence baseline |
| 1013 | DCIS/Bathnes | Bus Gate / Shuttle | config PDF + UTC form + as-built drawing + RAM + DWG zip | TBD | TBD | TBD | restriction / special layout |
| 1062 | DCIS/Bathnes | Multi-stream junction | config PDF + UTC form + SCOOT detectors + DWG zip | TBD | TBD | TBD | multi-source stream/stage mapping |
| 5040 | DCIS/Bathnes | MOVA junction | config PDF + UTC form + MOVA drawing + MOVA file + DWG zip | TBD | TBD | TBD | MOVA / detector evidence |

这样可以回答两个问题：

1. 单个 site 的 MAPEM 转换质量好不好。
2. 方法换到不同 site 类型、不同文件组合、不同可用字段和不同几何复杂度时是否 robust。

## 2. Weekly Plan

项目从第一周开始并行推进三条线：

- 数据线：Leeds + DCIS/Bathnes file inventory、file-format extraction、training / validation split、site-by-site testing。
- 原型线：Python package、file parsers、MAPEM field matching、evidence fusion、SiteModel、MAPEM output、validation report、review interface。
- 报告线：MAPEM requirements、field-source matrix、methodology、per-site quality metrics、robustness analysis、case study evidence、final recommendations。

### Timeline Summary

| 周次 | 日期 | 主要重点 | 对应 Plan Steps | 主要产出 |
| --- | --- | --- | --- | --- |
| Week 0 | 11–19 May 2026 | 项目理解、MAPEM 要求、Leeds 数据盘点 | Preparation, Step 1 | MAPEM requirement notes、Leeds data inventory、初版 project plan |
| Week 1 | 20–26 May 2026 | 更新工程流程、确认 MVP 范围和 parser architecture | Step 1, Step 2 preparation | file inventory design、MVP data scope、repository scaffold、parser design |
| Week 2 | 25–31 May 2026 | 自动 file inventory 和 file-format facts extraction | Step 1, Step 2 | `site_inventory.partial.json`, `extracted_facts.partial.json`, parser failure notes |
| Week 3 | 1–7 June 2026 | MAPEM field matching、field-source matrix、evidence fusion 和 MAPEM generator | Step 3, Step 4 | `mapped_evidence.partial.json`, `field_source_matrix.md`, 第一版 `site_model.json`, `mapem.json`, `mapem.asn1` |
| Week 4 | 8–14 June 2026 | Validation report、manual review workflow、单站点 quality score | Step 5, Step 7 | `validation_report.json`, `manual_review_items`, per-site quality score |
| Week 5 | 15–21 June 2026 | held-out robustness testing 和失败案例分析 | Step 6 | `robustness_summary.json`, per-site comparison、case study evidence、report draft |
| Final Week | 22–26 June 2026 | 最终修改、提交、展示和 poster | All steps | final report、prototype package、slides、poster、demo outputs |

### Week 0: 11–19 May 2026

**主题：** 项目理解、MAPEM 要求和 Leeds 数据盘点。

| 方面 | 工作内容 |
| --- | --- |
| 主要目标 | 理解 MAPEM 需要什么，以及 Leeds 当前有哪些可用数据。 |
| 关键任务 | 阅读 MAPEM/SPATEM 参考材料；区分 `mapem.asn1`、`mapem.json` 和 `validation_report.json`；盘点 6 个 Leeds sites；识别 site 类型、PDF/DWG 是否齐全、streams、stages、phases 和复杂度。 |
| 原型重点 | 建立初始仓库结构，定义第一版 `SiteModel` 结构。 |
| 报告重点 | 整理 MAPEM 数据要求说明和 Leeds site data inventory notes。 |
| 交付物 | MAPEM requirements document、Leeds site data inventory、第一版 project plan、client questions list。 |

### Week 1: 20–26 May 2026

**主题：** 更新工程流程，定义 MVP 范围，并准备 extraction architecture。

| 方面 | 工作内容 |
| --- | --- |
| 主要目标 | 把项目从直接按 PDF/CAD 生成 MAPEM，调整为 file inventory -> file-format facts extraction -> MAPEM field matching -> evidence fusion -> validation 的工程流程。 |
| 关键任务 | 盘点 Leeds + DCIS/Bathnes 新数据；明确 `file_path`、`file_type`、filename keywords、parser availability 等 file inventory 字段；明确每类 parser 第一版能抽取哪些 MAPEM 相关 facts；选择 development subset 和 held-out validation subset；保留 `397L` 作为简单 MVP baseline。 |
| 原型重点 | 准备 ingestion module 边界：PDF parser、DOCX parser、CAD/DXF parser、ZIP parser、RAM/TXT parser、GIS parser、field matcher、generators、validation。 |
| 报告重点 | 解释为什么先抽取 facts，再匹配 MAPEM fields；说明 file inventory 是根据文件路径、扩展名和文件名关键词自动生成，不要求人工先整理每个文件。 |
| 交付物 | file inventory design、parser module plan、更新后的 project plan、初版 quality metric design。 |

### Week 2: 25–31 May 2026

**主题：** file-format extraction 和第一版 field matching。

| 方面 | 工作内容 |
| --- | --- |
| 主要目标 | 自动建立 file inventory，并按文件格式抽取 MAPEM 相关 facts。 |
| 关键任务 | 为 Leeds + DCIS/Bathnes sites 自动生成 `site_inventory.partial.json`；从 PDF、DOCX、CAD/DXF、ZIP、TXT/8TX、GIS 中抽取 phases、stages、streams、intergreens、signalGroup candidates、lane geometry、stop lines、crossings、signal heads、detector/control notes 等 facts；记录 parser failures 和 low-confidence facts。 |
| 原型重点 | 生成 `site_inventory.partial.json` 和 `extracted_facts.partial.json`；每个 fact 保留 source file、evidence location 和 confidence。 |
| 报告重点 | 记录 file-format extraction 方法、限制，以及同一文件格式可能产生不同 fact types 的案例。 |
| 交付物 | site inventory files、extracted facts、parser failure notes、low-confidence fact examples。 |

### Week 3: 1–7 June 2026

**主题：** field-source matrix、evidence fusion 和 MAPEM generator。

| 方面 | 工作内容 |
| --- | --- |
| 主要目标 | 把 extracted facts 匹配到 MAPEM fields，生成 field-source matrix，并通过 evidence fusion 形成第一版 `SiteModel` 和 MAPEM outputs。 |
| 关键任务 | 建立 fact type -> MAPEM field 的 matching rules；将 lane candidates、stop lines、crossings、signal heads、phase/stage facts 匹配到 `refPoint`、`laneSet`、`nodeList`、`connectsTo`、`signalGroup` 等字段；生成 `mapped_evidence.partial.json` 和 `field_source_matrix.md`；识别 CRS/refPoint 问题；建立 lane-level geometry。 |
| 原型重点 | 从 `mapped_evidence.partial.json` 做 evidence fusion，生成第一版 `site_model.json`、`mapem.json` 和 `mapem.asn1` draft。 |
| 报告重点 | 解释 extracted facts、field-source matrix、`NodeXY`、`laneSet`、`connectsTo`、`signalGroup`、SiteModel 和 MAPEM output 的关系。 |
| 交付物 | mapped evidence、field-source matrix、第一版 SiteModel、第一版 MAPEM JSON、第一版 ASN.1-style output。 |

### Week 4: 8–14 June 2026

**主题：** Validation report、low-confidence review 和 quality scoring。

| 方面 | 工作内容 |
| --- | --- |
| 主要目标 | 让 prototype 能说明单个 site 的转换质量，以及哪些位置需要 human review。 |
| 关键任务 | 生成 `validation_report.json`；检查 `site_inventory.partial.json`、`extracted_facts.partial.json`、`mapped_evidence.partial.json`、`field_source_matrix.md` 和 `site_model.json`；加入 errors、warnings、scores 和 `manual_review_items`；定义 `review_id`、`current_value`、`candidate_values`、evidence location、confidence 和 suggested action；设计包含 `accept` 和 `correct` 的 review interface workflow。 |
| 原型重点 | 实现 file readability、fact extraction、field matching、fusion consistency、SiteModel completeness、lane references、signalGroup references、geometry confidence 和 manual review item generation 的 validation checks。 |
| 报告重点 | 定义 per-site quality scoring system，并解释为什么 `validation_report.json` 要和 `mapem.json` / `mapem.asn1` 分开。 |
| 交付物 | `validation_report.json`、manual review item format、per-site quality score、review interface workflow。 |

### Week 5: 15–21 June 2026

**主题：** 跨 site 类型的 robustness testing 和报告撰写。

| 方面 | 工作内容 |
| --- | --- |
| 主要目标 | 测试固定 pipeline 在不同 site 类型和不同文件组合上是否仍然有效。 |
| 关键任务 | 用 development subset 调整规则，用 held-out validation subset 测试；覆盖 Leeds PDF+DWG、DCIS/Bathnes config PDF+UTC form+drawing PDF+DWG zip+RAM/MOVA；比较 site success rate、parser failure count、field matching error count、evidence conflict count、manual intervention rate、worst site score 和 score variance。 |
| 原型重点 | 生成 `robustness_summary.json`，并根据失败案例记录 parser、field matching rules 和 fusion rules 的限制。 |
| 报告重点 | 撰写 case studies、file coverage analysis、robustness analysis、quality metrics、limitations 和 recommendations。 |
| 交付物 | `robustness_summary.json`、per-site quality table、case study outputs、60-80% report draft。 |

### Final Week: 22–26 June 2026

**主题：** 最终修改、提交、presentation 和 poster。

| 方面 | 工作内容 |
| --- | --- |
| 主要目标 | 完成 prototype、证据材料、report、presentation 和 poster。 |
| 关键任务 | 冻结 final pipeline；整理 demo outputs；定稿 `site_model.json`、`mapem.json`、`mapem.asn1`、`validation_report.json`、`robustness_summary.json` 和 quality scoring evidence；润色 final report；准备 demo narrative 和 poster。 |
| 原型重点 | 清理 README，运行 final tests，打包可复现实例和 demo outputs。 |
| 报告重点 | 完成 final report、reflective report、appendix、figures、tables、references 和 recommendations。 |
| 交付物 | Final project report、reflective report、prototype package、demo outputs、final slides、poster。 |

## 3. 当前最重要的结论

1. PDF、DOCX、DWG、DXF、GIS、LiDAR 只是文件格式，不等于最终 MAPEM 语义；同一个 PDF 可能抽出 phase/stage facts，也可能抽出 drawing/layout facts。
2. MAPEM 几何字段主要依赖 geometry facts，例如 `laneSet`、`nodeList`、stop lines、signal head locations。
3. MAPEM 控制语义主要依赖 phase/stage/control facts，例如 stages、phases、streams、`connectsTo.signalGroup`。
4. 新的 pipeline 应先按文件格式抽取 MAPEM 相关 facts，再把 facts 匹配到 MAPEM fields，最后通过 evidence fusion 生成 `SiteModel`。
5. 转换质量需要同时衡量 completeness、geometry、semantic、consistency、provenance、field matching、evidence fusion、manual effort 和 robustness。
6. 建议用 Leeds 的一部分 + DCIS/Bathnes 的一部分作为 development subset，再用剩余典型 sites 做 held-out validation，验证方法是否 general 和 robust。
