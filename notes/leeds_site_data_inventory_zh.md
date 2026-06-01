# Leeds City Council Site Data Inventory（本地中文版）

本文档基于当前本地文件夹 `Leeds City Council cite data/` 的 6 个 site 资料整理。
这些资料包含 confidential raw data，因此本文档先作为本地工作 notes，不推送到 GitHub。

## 1. 当前已有数据

每个 site 目前都有：

- 1 个 PDF signal specification。
- 1 个 DWG CAD drawing。

| Site | PDF | DWG |
| --- | --- | --- |
| 337L | `337L RODLEY RBOUT SPEC 15_6_15.pdf` | `UTC_716709_AJB_2a.dwg` |
| 378L | `378L Spec.pdf` | `733647-UTC-378L-01a 25-06-24.dwg` |
| 397L | `UTMC_397L_SPEC_02a.pdf` | `UTMC_300097_397L_04.dwg` |
| 573L | `573L v1 P 05_09_07.pdf` | `UTC-573L Cracked Egg.dwg` |
| 950L | `950L CH 16-05-24.pdf` | `UTC-950L A63 Selby Rd Ninelands La EDIT.dwg` |
| 982L | `982L-Spec-20_10_23.pdf` | `UTMC_716747_982L_01a-MorwickRemoved.dwg` |

## 2. Site-by-site 初步特征

以下信息来自 PDF 文本抽取和文件名。DWG 内部几何还没有解析；几何细节需要先转 DXF。

| Site | 路口 / 位置 | 初步类型 | 控制方式 / controller | Streams | Stages | Phases / signal labels | 初步复杂度 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 337L | Rodley Roundabout, A6120 Ring Rd / Rodley Lane / Calverley Lane | 大型 roundabout，多 stream | Telent Optima 32-phase ELV；UTC / CLF；Fixed Time fallback | 8 | 1-24 | A-Z + A1/A2；含 traffic、pedestrian、dummy phases | 最高 |
| 378L | A660 Headingley Lane near Richmond Avenue | Toucan crossing | Telent 4-phase Optima ELV；MOVA；UTC interface | PDF 有 Stream 1-4 模板引用；实际 stage data 主要在 Stream 1 | 0, 1, 2 | 表头为 A-F；含 pedestrian / toucan 信息 | 低 |
| 397L | Hyde Park Road Toucan near Brudenell Road | Toucan crossing | Telent Optima；MOVA / UTC interface | 1 | 1-2 | 表头为 A-D；pedestrian phase C 明确出现 | 最低，适合 MVP |
| 573L | A6120 / Century Way / Cracked Egg Roundabout | Roundabout，多 stream | Peek 24R TRX；5 streams；UTC / CLF fallback | 5 | 0-12 | A-R 等；含 traffic、pedestrian、dummy phase R | 高 |
| 950L | A63 Selby Road / Ninelands Lane | Signal junction with puffin upgrade | Swarco PTC1 8-phase；MOVA / VA；含 hurry call | PDF 有 Stream 1-4 引用 | 1-6；有 all-red / dummy / progression stages | 表头为 A-M；含 puffin phases、dummy phases | 中高 |
| 982L | A64 York Road / Scholes Lane, Scholes | 3-way junction with puffin crossings | Telent 8-phase Optima ELV；MOVA | PDF 有 Stream 1-4 模板引用 | 0, 1, 2, 5, 6 | 表头为 A-H；含 puffin E/F、Morwick Terrace all-red demand H | 中 |

## 3. 每个 site 当前能从 PDF 读到什么

### 337L

- 位置：Rodley Roundabout, A6120 Ring Rd / Rodley Lane / Calverley Lane。
- PDF 页数：50。
- 控制说明：所有 streams 需要同时运行 UTC；任何一个 stream 退出 UTC 时，其余 streams 也要切换到下一个可用控制模式。
- Streams：1 到 8。
- Stages：1 到 24。
- Use of phases 明确列出：
  - Traffic phases: A, B, D, E, F, H, I, K, M, N, P, R, S。
  - Pedestrian phases: C, G, J, L, O, Q, T。
  - Dummy phases: U, V, W, X, Y, Z, A1, A2。
- PDF 包含：
  - `USE OF PHASES`
  - `PHASES CONFLICTING/OPPOSING PHASES`
  - `USE OF STAGES - STAGE/PHASE RELATIONSHIP`
  - `PHASE INTERGREEN TIMES`

### 378L

- 位置：A660 Headingley Lane near Richmond Avenue。
- PDF 页数：25。
- 类型：Toucan crossing with kerbside and on-crossing detection。
- Controller：Telent 4-phase Optima ELV。
- 控制方式：MOVA；带 UTC interface。
- Stage data：主要是 `BASIC STAGE DATA FOR STREAM NO 1`。
- 抽取到的 stage numbers：0, 1, 2。
- Phase 表头：A-F。
- PDF 包含 MOVA loop positions、pedestrian phase demand、MOVA/UTC confirmation 等说明。

### 397L

- 位置：Hyde Park Road Toucan near Brudenell Road。
- PDF 页数：29。
- 类型：Toucan crossing。
- Controller：Telent Optima。
- 控制方式：MOVA / UTC interface。
- Streams：1。
- Stages：1-2。
- Phase 表头：A-D。
- 明确出现 pedestrian phase C。
- 这是当前最适合第一个 MVP 的 site，因为：
  - stream 少；
  - stage 少；
  - phase 少；
  - 路口类型简单；
  - MAPEM lane geometry 和 signal group mapping 的人工校核成本最低。

### 573L

- 位置：A6120 / Century Way / Cracked Egg Roundabout。
- PDF 页数：27。
- 类型：roundabout。
- Controller：Peek 24R TRX。
- 控制方式：5 streams；UTC mode；CLF fallback。
- Streams：1 到 5。
- Stages：0 到 12。
- Use of phases 中明确列出 traffic、pedestrian、dummy phases。
- PDF 含 stream 4 cross linking 说明，说明不同 stream 之间存在控制逻辑耦合。
- 复杂度高于普通 junction，但低于 337L。

### 950L

- 位置：A63 Selby Road / Ninelands Lane。
- PDF 页数：33。
- Controller：Swarco PTC1 8-phase。
- 控制方式：MOVA / VA。
- 类型：refurbished signal site with puffin pedestrian facilities。
- 特殊逻辑：
  - nearby fire station hurry call。
  - pedestrian forward calling。
  - dummy stages / dummy phases for progression。
- Phase 表头：A-M。
- PDF 有 `USE OF PHASES`、stage/phase relationship、conflict matrix、intergreen tables。

### 982L

- 位置：A64 York Road / Scholes Lane, Scholes, Leeds。
- PDF 页数：32。
- 类型：3-way junction with puffin crossings on south and east arms。
- Controller：Telent 8-phase Optima ELV。
- 控制方式：MOVA。
- Stages：0, 1, 2, 5, 6。
- Phase 表头：A-H。
- 特殊逻辑：
  - Quiescent All Red stage 6。
  - Morwick Terrace all-red demand, phase H / dummy DB。
  - Phase A & B always open and close together。
  - pedestrian phases E & F。

## 4. MAPEM 所需数据应该从哪里得到

| MAPEM 字段 / 内容 | 最可能来源 | 提取方法 | 备注 |
| --- | --- | --- | --- |
| `mapData.msgIssueRevision` | 项目配置 | 手动配置 | 初始可设为 1。 |
| `IntersectionGeometry.id.region` | 项目配置 / client metadata | 手动配置 | 当前示例用 UK/Leeds 相关占位值。 |
| `IntersectionGeometry.id.id` | site folder name / PDF title | 文件夹名 + PDF parser | 例如 397L、982L。 |
| `IntersectionGeometry.name` | PDF first page / title line | PDF text extraction | 可自动抽取后人工确认。 |
| `IntersectionGeometry.refPoint` | GIS / CAD georeference / manual point | DWG->DXF + GIS transform | PDF spec 一般不给精确经纬度。 |
| `IntersectionGeometry.laneWidth` | DWG lane geometry / default | CAD measurement 或默认值 | 如果 DWG 不可靠，先用配置默认值。 |
| `laneSet` | DWG/DXF | CAD layer parsing + geometry simplification | 这是 MAPEM 几何主体，不能只靠 PDF。 |
| `GenericLane.laneID` | 自动编号 | pipeline 生成 | 需要稳定编号，便于 `connectsTo` 引用。 |
| `GenericLane.ingressApproach / egressApproach` | CAD geometry + road names + manual interpretation | 几何方向聚类 + 人工校核 | Roundabout site 会更复杂。 |
| `GenericLane.laneAttributes.laneType` | CAD layer + PDF phase type + manual | layer rules + PDF cross-check | vehicle / pedestrian / cycle / bus 等要分清。 |
| `GenericLane.nodeList.nodes` | DWG/DXF lane centrelines | ODA 转 DXF；用 CAD parser 读 polyline | 需要转成相对 `refPoint` 的 offsets。 |
| `GenericLane.maneuvers` | PDF stage diagrams + road markings + geometry | PDF table/CV + CAD geometry inference | PDF 的 phase/stage 表本身不总是直接给 left/straight/right。 |
| `GenericLane.connectsTo` | CAD topology + movement interpretation | 几何连通分析 + stage/phase 约束 | 这是最需要人工校核的字段之一。 |
| `connectsTo.signalGroup` | PDF phase labels / use of phases / stage relationship | PDF table extraction | MAPEM 里 signalGroup 应该挂在 connection 上。 |
| `signalHeadLocations` | DWG signal symbols / PDF site map | CAD symbol extraction 或 PDF CV | MVP 可选，但对质量评估有用。 |
| `speedLimits` | external GIS / OSM / manual | GIS lookup 或手动录入 | PDF spec 不一定稳定提供。 |
| `restrictionList` | PDF notes / CAD markings | PDF parser + manual | MVP 可先不做。 |
| `dataParameters` / provenance | extraction pipeline | 自动记录 | 后续 validation_report 应该说明每个字段来源。 |
