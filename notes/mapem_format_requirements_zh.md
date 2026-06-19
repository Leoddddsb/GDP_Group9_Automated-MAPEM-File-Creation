# MAPEM 数据结构要求说明（中文版）

本文档是 `docs/mapem_format_requirements.md` 的中文版整理版。
重点不是完整翻译标准，而是帮助团队理解：

- MAPEM 的层级结构是什么。
- 每一层包含哪些内容。
- 我们从 CAD/PDF/GIS 提取的数据应该填到哪里。
- 当前 `SiteModel` 示例的结构是什么。

## 1. MAPEM 最核心的数据结构

MAPEM 可以先理解成下面这棵树：

```text
MAPEM / MapData
|
+-- intersections
    |
    +-- IntersectionGeometry
        |
        +-- id
        +-- revision
        +-- refPoint
        |   |
        |   +-- lat
        |   +-- lon
        |
        +-- laneWidth
        |
        +-- laneSet
            |
            +-- GenericLane
                |
                +-- laneID
                +-- ingressApproach / egressApproach
                +-- laneAttributes
                |   |
                |   +-- laneType
                |   +-- directionalUse
                |
                +-- maneuvers
                +-- nodeList
                |   |
                |   +-- NodeXY
                |   +-- NodeXY
                |   +-- NodeXY
                |
                +-- connectsTo
                    |
                    +-- target lane
                    +-- maneuver
                    +-- signalGroup
```

最重要的层级关系是：

```text
MapData
  -> IntersectionGeometry
      -> GenericLane
          -> nodeList       车道几何
          -> connectsTo     车道连接关系
              -> signalGroup    这个连接受哪个信号组控制
```

也就是说：

- `MapData` 是整个 MAPEM 文件。
- `IntersectionGeometry` 是一个路口。
- `GenericLane` 是路口里的一条车道。
- `nodeList` 描述这条车道长什么样。
- `connectsTo` 描述这条车道能连接到哪条下游车道。
- `signalGroup` 在 `connectsTo` 下面，描述某个 lane connection / movement 受哪个信号组控制。

## 2. 第一层：MapData

`MapData` 是 MAPEM 的最外层。

它大概长这样：

```text
MapData
|
+-- msgIssueRevision
+-- intersections
+-- restrictionList       可选
+-- dataParameters        可选
```

本项目 MVP 最需要：

| 字段 | 含义 | 是否需要 |
| --- | --- | --- |
| `msgIssueRevision` | MAPEM 版本号 | 需要 |
| `intersections` | 路口列表 | 需要 |
| `restrictionList` | 限制信息 | 可选 |
| `dataParameters` | 生成方法、机构等说明 | 可选 |

本项目大多数情况可以先做：

```text
一个 MapData
  包含一个 IntersectionGeometry
```

## 3. 第二层：IntersectionGeometry

`IntersectionGeometry` 表示一个具体路口。

它大概长这样：

```text
IntersectionGeometry
|
+-- id
|   |
|   +-- region
|   +-- id
|
+-- revision
+-- refPoint
|   |
|   +-- lat
|   +-- lon
|
+-- laneWidth
+-- laneSet
```

需要重点理解：

- `id`：这个路口的 ID。
- `revision`：这个路口拓扑版本。
- `refPoint`：路口参考点，通常放在路口冲突区附近。
- `laneWidth`：通用车道宽度。
- `laneSet`：这个路口包含的所有车道。

字段说明：

| 字段 | 含义 | 数据来源 |
| --- | --- | --- |
| `id.region` | 地区或道路管理机构编号 | 客户/手动设定 |
| `id.id` | 路口编号 | site ID、PDF、文件夹名 |
| `revision` | 路口版本 | 手动设定或版本管理 |
| `refPoint.lat` | 参考点纬度 | GIS/CAD/人工选择 |
| `refPoint.lon` | 参考点经度 | GIS/CAD/人工选择 |
| `laneWidth` | 默认车道宽度 | CAD/PDF/默认值 |
| `laneSet` | 车道集合 | CAD + PDF + 人工校核 |

`refPoint` 很重要。MAPEM 中很多几何点不是直接存原始 CAD 坐标，而是相对于 `refPoint` 的偏移。

## 4. 第三层：GenericLane

`GenericLane` 表示一条车道。

它大概长这样：

```text
GenericLane
|
+-- laneID
+-- ingressApproach / egressApproach
+-- laneAttributes
|   |
|   +-- laneType
|   +-- directionalUse
|
+-- maneuvers
+-- nodeList
+-- connectsTo
```

字段说明：

| 字段 | 含义 | 数据来源 |
| --- | --- | --- |
| `laneID` | 车道唯一 ID | 自动编号/人工确认 |
| `ingressApproach` | 入口 approach | 车道方向判断 |
| `egressApproach` | 出口 approach | 车道方向判断 |
| `laneAttributes.laneType` | 车道类型 | CAD 图层、PDF、人工判断 |
| `laneAttributes.directionalUse` | 入口/出口/双向 | CAD/GIS/人工判断 |
| `maneuvers` | 允许左转、直行、右转等 | PDF phase/stage 图、道路标线 |
| `nodeList` | 车道中心线几何 | CAD/DXF/GIS |
| `connectsTo` | 连接到哪些下游车道 | 几何 + movement 判断 |

简单理解：

```text
GenericLane = 一条车道的 ID + 类型 + 方向 + 几何 + movement + 连接关系
```

## 5. nodeList：车道几何

`nodeList` 描述车道中心线。

结构如下：

```text
nodeList
|
+-- NodeXY 1
+-- NodeXY 2
+-- NodeXY 3
+-- ...
```

每个 `NodeXY` 是一个点。多个点连起来，就是这条 lane 的中心线。

示意：

```text
Lane centreline

Node 1 ------ Node 2 ------ Node 3
```

本项目里的中间 JSON 可以先这样表示：

```json
{
  "laneID": 1,
  "nodeList": {
    "nodes": [
      { "x": 0.0, "y": -40.0 },
      { "x": 0.0, "y": -10.0 },
      { "x": 0.0, "y": 0.0 }
    ]
  }
}
```

注意：

- 这些点应该是相对于 `refPoint` 的局部坐标。
- 不应该直接把 CAD 原始坐标塞进 MAPEM。
- 节点太少会不准确，节点太多会让 MAPEM 变大。

## 6. connectsTo：车道连接关系

`connectsTo` 描述一条入口车道进入路口后，可以去到哪条出口车道。

结构如下：

```text
GenericLane 1
|
+-- connectsTo
    |
    +-- connectingLane: Lane 2
    +-- maneuver: straight
    +-- signalGroup: 1
```

也可以理解成：

```text
Lane 1  --straight / signalGroup 1-->  Lane 2
```

MVP 至少需要知道：

| 信息 | 例子 |
| --- | --- |
| 源车道 | Lane 1 |
| 目标车道 | Lane 2 |
| movement | straight / left / right |
| signal group | Signal Group 1 |

这部分通常不能只靠 CAD 自动判断，往往需要结合：

- PDF stage diagram
- phase table
- road marking
- 人工校核

## 7. signalGroup：信号组

MAPEM 不描述信号配时，但它要引用 signal group。  
这样 MAPEM 的拓扑才能和 SPATEM 的信号状态对应。

结构可以先理解成：

```text
SignalGroup
|
+-- signalGroupID
+-- phaseLabel
+-- controlledLanes
+-- description
```

例子：

```text
SignalGroup 1
|
+-- phaseLabel: A
+-- controlledLanes: Lane 1
+-- description: northbound ahead movement
```

数据来源通常是 PDF：

- USE OF PHASES
- STAGE / PHASE 表
- CONFLICTING PHASES
- stage arrows
- phase label A/B/C/D

## 8. signalHeadLocations：可选扩展

如果能从 CAD 或 PDF 中提取信号灯头位置，可以加入：

```text
signalHeadLocations
|
+-- nodeXY
+-- nodeZ
+-- signalGroupID
```

这对质量评估很有帮助，但不是第一个 MVP 的必需字段。

## 9. 本项目最小可行 MAPEM

第一个能跑通的 MAPEM，至少应该包含：

```text
MapData
|
+-- msgIssueRevision
+-- intersections
    |
    +-- IntersectionGeometry
        |
        +-- id
        +-- revision
        +-- refPoint
        +-- laneWidth
        +-- laneSet
            |
            +-- GenericLane
                |
                +-- laneID
                +-- laneType
                +-- ingressApproach / egressApproach
                +-- nodeList
                +-- maneuvers
                +-- connectsTo
                    |
                    +-- target lane
                    +-- maneuver
                    +-- signalGroup
```

换句话说，MVP 不需要一次性覆盖全部 MAPEM 标准，但必须把下面几件事讲清楚：

1. 这是哪个路口。
2. 路口参考点在哪里。
3. 有哪些车道。
4. 每条车道的几何形状是什么。
5. 每条入口车道允许什么 movement。
6. 每条入口车道连接到哪条出口车道。
7. 这些 movement 受哪个 signal group 控制。

## 10. 数据来源到 MAPEM 字段的映射

| MAPEM 内容 | 主要来源 |
| --- | --- |
| 路口 ID | 文件夹名、PDF 标题、客户元数据 |
| `refPoint` | CAD/GIS 坐标、人工选择 |
| lane geometry / `nodeList` | DWG/DXF、GIS |
| lane type | CAD 图层、PDF site map、人工判断 |
| stop line | DWG/DXF、PDF site map |
| maneuvers | PDF stage arrows、phase 描述、道路标线 |
| connectsTo | 车道几何 + movement 判断 |
| signal groups | PDF phase tables、信号标签 |
| signal head locations | CAD 符号、PDF 图、CV |
| restrictions | PDF 说明、道路标线 |
| speed limits | PDF、OSM/GIS、人工录入 |

## 11. 当前 SiteModel 是 MAPEM 示例

当前仓库里的 `examples/site_model.example.json` 是一个 MAPEM-style 示例。  
它不是从真实 Leeds 数据自动生成的，而是用来展示我们希望各模块最终输出的数据长什么样。

这个示例的真实结构如下：

```text
SiteModel
|
+-- mapData
|   |
|   +-- msgIssueRevision
|   +-- intersections
|       |
|       +-- IntersectionGeometry
|           |
|           +-- id
|           |   |
|           |   +-- region
|           |   +-- id
|           |
|           +-- revision
|           +-- refPoint
|           |   |
|           |   +-- lat
|           |   +-- lon
|           |   +-- elevation        可选
|           |
|           +-- laneWidth            可选但推荐
|           +-- speedLimits          可选
|           +-- signalHeadLocations  可选
|           |
|           +-- laneSet
|               |
|               +-- GenericLane
|                   |
|                   +-- laneID
|                   +-- name
|                   +-- ingressApproach / egressApproach
|                   +-- laneAttributes
|                   |   |
|                   |   +-- laneType
|                   |   +-- directionalUse
|                   |   +-- sharedWith
|                   |
|                   +-- maneuvers
|                   +-- nodeList
|                   |   |
|                   |   +-- nodes
|                   |       |
|                   |       +-- NodeXY
|                   |       +-- NodeXY
|                   |
|                   +-- connectsTo
|                       |
|                       +-- Connection
|                           |
|                           +-- connectingLane
|                           |   |
|                           |   +-- lane
|                           |   +-- maneuver
|                           |
|                           +-- signalGroup
|                           +-- connectionID
|
+-- sourceNotes
```

简化 JSON 视图：

```json
{
  "mapData": {
    "msgIssueRevision": 1,
    "intersections": [
      {
        "name": "Synthetic three-arm signal junction",
        "id": {
          "region": 826,
          "id": "SYNTH-001"
        },
        "revision": 1,
        "refPoint": {
          "lat": 53.800755,
          "lon": -1.549077
        },
        "laneWidth": 3.25,
        "laneSet": [
          {
            "laneID": 1,
            "name": "Northbound ingress",
            "ingressApproach": 1,
            "laneAttributes": {
              "laneType": "vehicle",
              "directionalUse": "ingress",
              "sharedWith": []
            },
            "maneuvers": ["straight", "right"],
            "nodeList": {
              "nodes": [
                { "x": 0.0, "y": -40.0 },
                { "x": 0.0, "y": -10.0 },
                { "x": 0.0, "y": 0.0 }
              ]
            },
            "connectsTo": [
              {
                "connectingLane": {
                  "lane": 2,
                  "maneuver": "straight"
                },
                "signalGroup": 1,
                "connectionID": 1
              }
            ]
          }
        ],
        "signalHeadLocations": [
          {
            "nodeXY": { "x": -1.5, "y": -8.0 },
            "signalGroupID": 1
          }
        ]
      }
    ],
    "dataParameters": {
      "processMethod": "synthetic example",
      "processAgency": "Imperial GDP Group 9"
    }
  },
  "sourceNotes": [
    "Synthetic non-confidential example for repository smoke tests."
  ]
}
```

## 12. 当前仍然不是完整生产级 MAPEM 的地方

虽然现在的 `SiteModel` 层级已经更接近 MAPEM 标准，但它仍然不是完整生产级编码器。

仍然需要后续完善：

- 更严格的 ASN.1 枚举和 bit string 表达。
- `NodeXY` 的真实 MAPEM delta 类型编码。
- lane width delta。
- 更完整的 regional extensions。
- 每个字段的数据来源记录，即 provenance。
- 更严格的几何质量检查，例如节点间距、偏移范围、车道连接合理性。
- 真正可被标准工具解析的 ASN.1 编码，而不仅是当前的 ASN.1-style 文本输出。

下一步建议优先补充：

```text
source provenance
|
+-- 每个 lane 来自哪个 CAD 图层
+-- 每个 movement 来自哪个 PDF 表格或 stage diagram
+-- 每个 signalGroup 来自哪个 phase label
+-- 哪些字段经过人工校核
```

这样后续做 validation_report 时，才能清楚说明：

- 哪些内容是自动提取的
- 哪些内容是人工修正的
- 哪些内容缺失或不可靠
