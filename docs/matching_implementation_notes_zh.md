# Matching 实现记录

本文记录 573L 调试过程中加入的 matching 侧修补逻辑。之后如果同事更新
`matching_rules.yaml`、`generator_overlay.json` 或 `transforms_overlay.py`，需要保留这些逻辑。

## 已更新文件

- `src/mapemgen/matching/matching_rules.yaml`
- `src/mapemgen/matching/generator_overlay.json`
- `src/mapemgen/matching/transforms_overlay.py`
- `src/mapemgen/matching/matching_engine.py`
- `src/mapemgen/matching/ingest_adapter.py` 没有被同事文件覆盖，之前加的 adapter 修补继续保留。

## Intersection ID

`ingest_adapter.py` 会从 extraction 输出里的 `site_id` 注入
`official_intersection_id_from_cad`。

例如 `573L` 会通过 transform `extract_int_from_site_code` /
`extract_int_from_identifier` 转成 MAPEM intersection id `573`。

这样可以避免源文件里没有干净的 intersection id fact 时，最终出现 `id.id = null`。

## Approach Assignment

assignment 阶段会为每条 lane 生成 `approach_assignment_candidate_from_cad`。
这些 facts 必须继续作为以下字段的来源：

- `mapData.intersections[].laneSet[].ingressApproach`
- `mapData.intersections[].laneSet[].egressApproach`
- `mapData.intersections[].laneSet[].laneAttributes.directionalUse`

当前规则：

- 有 CAD stop line 的 lane 作为 `ingress`。
- 如果同一个 approach 中存在 stop-line lane，则同 approach 里没有 stop line 的 lane 可以作为 `egress`，并标记 `direction_basis = approach_stop_line_complement`。
- 如果没有明确 direction，也没有可靠 geometry prepass direction，则保持 unresolved，不强行猜测。
- 同一条 lane 不能同时有 `ingressApproach` 和 `egressApproach`。

`generator_overlay.json` 里必须保留这两个 transform 映射：

```json
"mapData.intersections[].laneSet[].ingressApproach||approach_assignment_candidate_from_cad": [
  "approach_id_ingress"
],
"mapData.intersections[].laneSet[].egressApproach||approach_assignment_candidate_from_cad": [
  "approach_id_egress"
]
```

## Directional Use

`transforms_overlay.py` 覆盖了 `directional_use_from_label` 对 dict payload 的处理：

- payload 有 `direction: ingress` 时输出 `ingress`。
- payload 有 `direction: egress` 时输出 `egress`。
- payload 没有明确 direction 时输出 `unknown`。

这个修补很重要，因为 base transform 会把 payload dict 转成字符串；如果里面有
`approach_ref`，可能因为包含 `approach` 这个词而把所有 lane 误判为 ingress。

`matching_engine.py` 也对 `laneAttributes.directionalUse` 做了选择保护：

- 如果候选里存在明确值 `10`、`01` 或 `11`，`00 unknown` 不能只靠多数胜出。
- 如果所有候选都是 unknown，则仍允许输出 `00`。

## RefPoint 和 CRS

同事的 overlay 增加了 `junction_centre_lat` 和 `junction_centre_long`。
`matching_engine._analyze_lanes()` 现在会在 lane geometry prepass 中计算
`resolved["junction_centre"]`，并把 CAD BNG 坐标转换成 WGS84 的 1e7 整数格式。

这样规则可以用同一个 junction-level centre 填充：

- `mapData.intersections[].refPoint.lat`
- `mapData.intersections[].refPoint.long`

避免每条 lane 各自拿 centroid 作为 refPoint，导致多个 refPoint 候选互相冲突。

## Transform 兼容修补

overlay 里还保留了以下兼容 wrapper：

- `relative_to_refpoint`：如果 `refPoint` 是 WGS84，经纬度会先转回 BNG，再和 CAD 点计算 offset。
- `choose_node_xy_precision`：既接受单个 offset，也接受 offset 列表。
- `approach_id_ingress` / `approach_id_egress`：先尊重 payload 里的明确 `direction`，再回退到 geometry prepass。

这些修补用于避免 payload shape 不一致导致 `pending_transform`。

## OSTN15 Grid 虚拟环境操作

MAPEM 当前使用 British National Grid `EPSG:27700` 转 WGS84 `EPSG:4326`。
为了让 pyproj 使用英国区域最准确的 OSTN15 transformation，需要把 grid 文件安装到当前虚拟环境。

本环境实际使用的命令：

```powershell
.\mapem313\Scripts\python.exe -m pyproj sync --file uk_os_OSTN15_NTv2_OSGBtoETRS.tif --target-directory C:\Users\leovo\Desktop\GDP\mapem313\Lib\site-packages\pyproj\proj_dir\share\proj
```

安装后文件位置：

```text
C:\Users\leovo\Desktop\GDP\mapem313\Lib\site-packages\pyproj\proj_dir\share\proj\uk_os_OSTN15_NTv2_OSGBtoETRS.tif
```

验证命令：

```powershell
@'
from pyproj.transformer import TransformerGroup
g = TransformerGroup("EPSG:27700", "EPSG:4326")
print("OSTN15 best_available:", g.best_available)
print("unavailable operations:", len(g.unavailable_operations))
'@ | .\mapem313\Scripts\python.exe -
```

期望输出：

```text
OSTN15 best_available: True
unavailable operations: 0
```

安装成功后，matching 不应再出现下面这个 warning：

```text
Best transformation is not available due to missing Grid(...uk_os_OSTN15_NTv2_OSGBtoETRS.tif...)
```

如果以后删除或重建 `mapem313` 虚拟环境，需要重新执行上面的 `pyproj sync` 命令。

## 573L 验证结果

合并同事文件并保留上述修补后，573L 当前结果：

```text
matching: fields=236 ok=226 manual_review=10 pending_transform=0
fusion: leaves=235 accepted=147 provisional=0 gaps=88 conflicts=35 consistency_errors=0
lanes: 32
ingressApproach: 11
egressApproach: 7
同一条 lane 同时有 ingress/egress: 0
directionalUse: 10 -> 11, 01 -> 7, 00 -> 14
connectsTo: 0
```

`connectsTo` 仍然 unresolved，原因是 assignment 目前还缺少可靠的
`movement_lane_mappings`、`semantic_assignments` 或 `lane_connection_candidate_*` 证据。
