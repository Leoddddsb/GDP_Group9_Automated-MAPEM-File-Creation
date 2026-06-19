# MAPEM 匹配候选值选择逻辑

本文说明 Step 3 matching 阶段在多个 candidate facts 同时匹配到同一个 MAPEM field 时，系统可以采用的两种最终值选择逻辑。

这份说明的目的，是把 selection policy 明确写出来，方便客户选择：matcher 应该更像一个 evidence-fusion engine，还是更像一个保守的 priority-based mapper。

## 背景

Step 2 extraction 会从 CAD、PDF、DOCX、RAM/8TX、GIS、ZIP 成员文件和其他输入文件中提取 facts。

Step 3 matching 使用 `matching_rules.yaml` 判断哪些 extracted facts 可以填充哪些 MAPEM fields。很多情况下，同一个 MAPEM field 会有多个 candidate facts。

例如：

```text
mapData.intersections[].refPoint.lat
mapData.intersections[].refPoint.long
mapData.intersections[].laneSet[].laneAttributes.laneType
mapData.intersections[].laneSet[].connectsTo[].signalGroup
```

当多个 candidate facts 同时存在时，matcher 需要决定：

```text
1. 最终选择哪个 candidate value？
2. 哪些 facts 支持这个 selected value？
3. 哪些 facts 和它冲突？
4. 应该报告怎样的 confidence？
5. 这个结果是否需要 manual review？
```

目前有两种可选的 candidate selection policy。

## Option A: 基于 Final Score 的选择逻辑

这套逻辑会先为每个 candidate fact 计算一个综合分数，然后选择 `final_score` 最高的 candidate 作为最终 MAPEM field value。

综合分数由三部分组成：

```text
final_score =
  extract_weight  * extract_confidence_score
+ conflict_weight * conflict_agreement_score
+ priority_weight * source_priority_score
```

建议初始权重：

```text
extract_confidence_score: 15%
conflict_agreement_score: 35%
source_priority_score:    50%
```

### 分数组成

`extract_confidence_score`

来自 Step 2 extraction。它表示 parser 对该 fact 提取结果本身的可靠性判断。

例如：

```text
PDF table row extraction: medium/high confidence
OCR text extraction: lower confidence
CAD geometry extraction: medium/high confidence
GIS fallback extraction: medium/low confidence
```

`conflict_agreement_score`

表示当前 candidate 是否和同一个 MAPEM field 下的其他 candidates 一致。

conflict score 必须在同一个 `target_path + object_scope` 分组内计算。不同 lane、不同 lane connection、不同 intersection 的 candidates 不能互相比较。

初始规则可以使用简单多数一致性：

```text
conflict_agreement_score = agreeing_candidate_count / candidate_count
```

agreement 的判断方式取决于 `matching_rules.yaml` 中配置的 field type：

```text
coordinate fields:
  两个候选值的距离在配置的米级 tolerance 内，则认为一致。

node_delta fields:
  两个 node offset 的距离在配置的米级 tolerance 内，则认为一致。

integer_id fields:
  必须完全相等才认为一致。

enum fields:
  必须完全相等才认为一致。

angle fields:
  角度差在配置的 degree tolerance 内，则认为一致。
```

示例：

```text
6 个 candidates 匹配到同一个 field。
其中 5 个和 candidate A 一致。
1 个和 candidate A 不一致。

candidate A conflict_agreement_score = 5 / 6 = 0.83
```

`source_priority_score`

来自 `matching_rules.yaml` 中定义的 source priority。

它会把 priority label 转换成数值。一个简单的初始映射可以是：

```text
P1 = 1.00  最高优先级官方来源
P2 = 0.75  次级来源
P3 = 0.50  较低优先级支持来源
F  = 0.25  fallback 来源
```

priority score 在 `final_score` 中占最大权重，因此官方来源或更可信来源仍然具有最大影响力。

具体数值后续可以根据测试数据调整，但 ranking 必须始终保持：

```text
P1 > P2 > P3 > F
```

### 选择流程

```text
1. 使用 matching_rules.yaml 找到每个 MAPEM field 的 candidate facts。
2. 按 target_path 和 object_scope 分组。
3. 对每个 candidate 计算 extract_confidence_score。
4. 对每个 candidate 计算 conflict_agreement_score。
5. 对每个 candidate 计算 source_priority_score。
6. 计算 final_score。
7. 选择 final_score 最高的 candidate。
8. 输出 chosen value、confidence breakdown、conflict details、corroborating facts、rejected facts 和 decision status。
```

### 优点

```text
1. 灵活。
   最终选择可以同时考虑 parser confidence、source priority 和 cross-source agreement。

2. 更适合 evidence fusion。
   如果高优先级来源本身较弱或和其他来源明显不一致，系统有机会选择被更多 evidence 支持的低优先级来源。

3. 输出解释性更强。
   系统可以说明最终选择主要是因为 priority 高、和其他 facts 一致，还是 extraction quality 高。

4. 后期可调。
   权重可以在真实数据测试后继续调整。
```

### 缺点

```text
1. 更复杂。
   客户需要理解 final_score 是如何计算出来的。

2. 权重有一定主观性。
   例如 15/35/50 只是初始设定，必须通过真实站点数据验证。

3. 官方来源优先级不是绝对的。
   如果另一个 candidate 的综合分数更高，高优先级来源可能被覆盖。

4. debug 成本更高。
   当选择结果不符合预期时，需要检查三个组成分数和权重配置。
```

## Option B: Priority First With Confidence Floor

这套逻辑会先按照 source priority 对 candidates 排序，然后从最高优先级 candidate 开始，检查其两部分组成的 reported confidence 是否高于最低门槛 `confidence_floor`。

第一个通过 floor 的 candidate 会被选为最终值。

这套逻辑和当前 `SourceSelector` 的实现最接近。

在 Option B 中，confidence 不是三部分 final score。它由两部分组成：

```text
reported_confidence =
  extract_weight  * extract_confidence_score
+ conflict_weight * conflict_agreement_score
```

source priority 不属于 Option B 的 confidence score。priority 先用于排序 candidates，然后 two-part confidence 用于判断该 candidate 是否达到最低质量门槛。

示例初始权重：

```text
extract_confidence_score: 40%
conflict_agreement_score: 60%
```

这些权重后续可以通过测试数据调整。关键点是：`confidence_floor` 不只是检查 extraction confidence，它检查的是 candidate 在同时考虑 extraction reliability 和 conflict agreement 后，整体质量是否足够。

### 选择流程

```text
1. 使用 matching_rules.yaml 找到每个 MAPEM field 的 candidate facts。
2. 按 target_path 和 object_scope 分组。
3. 按 source priority 排序：
   P1 -> P2 -> P3 -> F
4. 从最高优先级 candidate 开始计算 two-part reported confidence：
   extract_confidence_score + conflict_agreement_score。
5. 检查该 reported confidence 是否高于 confidence_floor。
6. 选择第一个通过 floor 的 candidate。
7. 后续也通过 floor 的 candidates 记录为 corroborating evidence。
8. 低于 floor 的 candidates 记录为 rejected。
9. conflict 信息参与 floor 检查，但通过 floor 的 candidates 仍然按 source priority 排序。
```

### 示例

```text
Case 1:
P1 candidate extract_score = 0.80
P1 candidate conflict_score = 0.20
P1 reported_confidence = 0.44

P2 candidate extract_score = 0.70
P2 candidate conflict_score = 0.90
P2 reported_confidence = 0.82

confidence_floor = 0.60

Result:
P1 被 rejected。
P2 被 selected。
```

```text
Case 2:
P1 candidate extract_score = 0.70
P1 candidate conflict_score = 0.80
P1 reported_confidence = 0.76

P2 candidate extract_score = 0.95
P2 candidate conflict_score = 0.90
P2 reported_confidence = 0.92

confidence_floor = 0.60

Result:
P1 被 selected。
P2 被记录为 corroborating evidence。
```

在这套逻辑中，低优先级来源即使 extraction confidence 更高，也不会自动覆盖一个已经通过 floor 的高优先级来源。

### Confidence 输出

在这套逻辑中，confidence 仍然可以和 decision 分开输出。

例如：

```json
{
  "confidence": {
    "reported_confidence": 0.78,
    "extract_score": 0.70,
    "conflict_score": 0.83,
    "weights": {
      "extract": 0.40,
      "conflict": 0.60
    }
  },
  "decision": {
    "status": "matched",
    "reason": "highest_priority_candidate_above_floor"
  }
}
```

关键区别是：`conflict_score` 会参与 floor 检查，所以一个高优先级 candidate 如果和其他 sources 严重不一致，也可能无法通过 floor。

但 conflict 不会重新排序已经通过 floor 的 candidates。通过 floor 之后，仍然由 source priority 决定谁先被选择。

### 优点

```text
1. 简单、稳定、容易解释。
   系统使用最高优先级且质量达标的来源。

2. 保守。
   当官方或高可信来源达到最低 extraction confidence 时，系统优先采用这些来源。

3. 更容易验证。
   如果结果不符合预期，客户可以检查 priority order、two-part confidence 和 confidence_floor。

4. 运行稳定。
   priority ordering 和 confidence floor 被分开处理，因此更容易 debug。
```

### 缺点

```text
1. 相比完整 final-score selection 不够灵活。
   如果高优先级来源和低优先级来源都通过 floor，系统仍会先选择高优先级来源。

2. conflict 影响 eligibility，但不影响 ordering。
   较差的 conflict score 可以让 candidate 低于 floor，但不会重新排序已经通过 floor 的 candidates。

3. 高度依赖 priority 配置质量。
   如果 matching_rules.yaml 中的 priority 配错，matcher 会系统性偏向错误来源。

4. confidence_floor 和 two-part confidence 权重仍然需要调试。
   floor 太低会让较弱的高优先级 fact 通过。
   floor 太高会误拒可用 fact。
```

## 两套逻辑都应遵守的共同规则

无论选择哪套 selection policy，都建议保留以下共同规则。

### 必须尊重 Object Scope

有些 MAPEM fields 不是全局字段，而是属于某个具体对象实例。

例如：

```text
laneSet[].laneAttributes.laneType
```

这是每一条 lane 自己的 field，不是整个 junction 的全局 field。

```text
laneSet[].connectsTo[].signalGroup
```

这是每个 lane connection 自己的 field，不是所有 signal groups 的全局 field。

因此 candidates 必须按照以下组合分组：

```text
target_path + object_scope
```

object scope 可以包括：

```text
intersection_ref
lane_ref
connection_ref
node_ref
```

不同 lane 或不同 connection 的 candidates 不能被当成同一个 field 来比较 conflict。

### Confidence 和 Decision 必须分开

confidence 说明系统有多相信 selected value。

decision 说明 matcher 对这个 value 做了什么处理。

示例：

```json
{
  "confidence": {
    "extract_score": 0.72,
    "conflict_score": 0.66,
    "priority_score": 1.0,
    "final_score": 0.81
  },
  "decision": {
    "status": "matched_with_conflict",
    "reason": "selected_candidate_has_high_priority_but_some_disagreement_exists"
  }
}
```

这种分离很重要，因为一个值可以被选中，但仍然可能需要人工复核。

### 高优先级冲突必须暴露

如果一个 P1 candidate 和多个 P1 或 P2 candidates 严重冲突，matcher 不应该隐藏这个冲突。

根据选择的 policy，系统可以仍然选择 P1 candidate，但 decision status 应该体现需要 review。

示例 statuses：

```text
matched
matched_with_conflict
manual_review_required
unresolved
pending_transform
```

### 必须保留 Provenance

每个 selected value 都必须能追溯到产生它的 facts。

每条 mapped evidence record 应保留：

```text
fact_id
fact_name
source_file
evidence_location
confidence
payload
```

### 必须保留 Corroborating 和 Rejected Evidence

matcher 不应该只输出最终选择的 value。

它还应该记录：

```text
corroborating facts
rejected facts
rejection reason
conflict details
priority used
priority spread
```

这样系统才具备可审计性，也方便 manual review。

## 给客户的决策问题

客户可以在以下两个原则之间选择：

```text
Option A:
是否希望 matcher 像 evidence-fusion engine 一样，
由 source priority、extraction confidence 和 cross-source agreement
共同决定 selected value？
```

```text
Option B:
是否希望 matcher 像保守的 priority-based mapper 一样，
在 candidate 通过由 extraction confidence 和 conflict agreement 组成的
two-part confidence floor 后，选择最高优先级且质量达标的来源？
```
