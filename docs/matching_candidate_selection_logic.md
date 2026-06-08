# MAPEM Matching Candidate Selection Logic

This note explains two possible ways to select the final MAPEM field value when Step 3 matching finds multiple candidate facts for the same MAPEM field.

The purpose is to make the selection policy explicit so the client can choose whether the matcher should behave as an evidence-fusion engine or as a conservative priority-based mapper.

## Background

Step 2 extraction produces facts from CAD, PDF, DOCX, RAM/8TX, GIS, ZIP members, and other input files.

Step 3 matching uses `matching_rules.yaml` to decide which extracted facts can populate each MAPEM field. In many cases, more than one fact can match the same target field.

Example targets include:

```text
mapData.intersections[].refPoint.lat
mapData.intersections[].refPoint.long
mapData.intersections[].laneSet[].laneAttributes.laneType
mapData.intersections[].laneSet[].connectsTo[].signalGroup
```

When multiple candidate facts exist, the matcher must decide:

```text
1. Which candidate value should be selected?
2. Which facts support the selected value?
3. Which facts conflict with it?
4. What confidence should be reported?
5. Does the result need manual review?
```

There are two candidate selection policies.

## Option A: Final Score Based Selection

This policy calculates a final score for every candidate fact, then selects the candidate with the highest `final_score`.

The score has three components:

```text
final_score =
  extract_weight  * extract_confidence_score
+ conflict_weight * conflict_agreement_score
+ priority_weight * source_priority_score
```

Suggested initial weights:

```text
extract_confidence_score: 15%
conflict_agreement_score: 35%
source_priority_score:    50%
```

### Score Components

`extract_confidence_score`

This comes from Step 2 extraction. It represents how reliable the parser thinks the extracted fact is.

Examples:

```text
PDF table row extraction: medium/high confidence
OCR text extraction: lower confidence
CAD geometry extraction: medium/high confidence
GIS fallback extraction: medium/low confidence
```

`conflict_agreement_score`

This measures whether the candidate agrees with other candidates matched to the same MAPEM field.

The conflict score is calculated within the same `target_path + object_scope` group. Candidates for different lanes, different lane connections, or different intersections must not be compared with each other.

As an initial rule, the score can use simple majority agreement:

```text
conflict_agreement_score = agreeing_candidate_count / candidate_count
```

The agreement test depends on the field type configured in `matching_rules.yaml`:

```text
coordinate fields:
  candidates agree if their distance is within the configured metre tolerance

node_delta fields:
  candidates agree if their node offset distance is within the configured metre tolerance

integer_id fields:
  candidates agree only if the values are exactly equal

enum fields:
  candidates agree only if the values are exactly equal

angle fields:
  candidates agree if their angular difference is within the configured degree tolerance
```

Example:

```text
6 candidates match one field.
5 agree with candidate A.
1 disagrees.

candidate A conflict_agreement_score = 5 / 6 = 0.83
```

`source_priority_score`

This comes from the source priority in `matching_rules.yaml`.

The score translates the priority label into a numeric value. A simple initial mapping is:

```text
P1 = 1.00  highest-priority official source
P2 = 0.75  secondary source
P3 = 0.50  lower-priority supporting source
F  = 0.25  fallback source
```

The priority score gives the largest contribution to `final_score`, so official or more trusted sources still carry the most influence.

The exact numeric mapping can be tuned later, but the ranking must remain consistent with the source hierarchy:

```text
P1 > P2 > P3 > F
```

### Selection Flow

```text
1. Use matching_rules.yaml to find candidate facts for each MAPEM field.
2. Group candidates by target_path and object_scope.
3. For each candidate, calculate extract_confidence_score.
4. For each candidate, calculate conflict_agreement_score.
5. For each candidate, calculate source_priority_score.
6. Calculate final_score.
7. Select the candidate with the highest final_score.
8. Output the chosen value, confidence breakdown, conflict details, corroborating facts, rejected facts, and decision status.
```

### Advantages

```text
1. Flexible.
   The selected value can reflect parser confidence, source priority, and cross-source agreement.

2. Better suited to evidence fusion.
   If a high-priority source is weak or inconsistent, a strongly supported lower-priority value may be selected.

3. More informative output.
   The system can explain whether the result was chosen because of source priority, agreement with other facts, or extraction quality.

4. Tunable after testing.
   The weights can be adjusted once real project data is available.
```

### Disadvantages

```text
1. More complex.
   The client must understand how the final score is calculated.

2. Weighting is partly subjective.
   Initial weights such as 15/35/50 need validation against real sites.

3. Official source priority is not absolute.
   A high-priority source can be overridden if the scoring model gives another candidate a higher final_score.

4. Harder to debug.
   Unexpected selections require checking three component scores and the weight configuration.
```

## Option B: Priority First With Confidence Floor

This policy sorts candidates by source priority first. It then selects the first candidate whose two-part reported confidence is above a configured minimum floor.

This is the logic currently closest to the existing `SourceSelector` implementation.

In this option, confidence is not a three-part final score. It has two parts:

```text
reported_confidence =
  extract_weight  * extract_confidence_score
+ conflict_weight * conflict_agreement_score
```

Source priority is not part of the confidence score in Option B. Priority is used first to order candidates. The two-part confidence is then used as a quality floor.

Example initial weights:

```text
extract_confidence_score: 40%
conflict_agreement_score: 60%
```

These weights can be tuned after testing. The important point is that `confidence_floor` is not only checking extraction confidence. It is checking whether the candidate has enough quality after considering both extraction reliability and conflict agreement.

### Selection Flow

```text
1. Use matching_rules.yaml to find candidate facts for each MAPEM field.
2. Group candidates by target_path and object_scope.
3. Sort candidates by source priority:
   P1 -> P2 -> P3 -> F
4. Starting from the highest-priority candidate, calculate its two-part reported confidence:
   extract_confidence_score + conflict_agreement_score.
5. Check whether that reported confidence is above confidence_floor.
6. Select the first candidate that passes the floor.
7. Later candidates that also pass the floor become corroborating evidence.
8. Candidates below the floor are rejected.
9. Conflict information contributes to the floor check, but passing candidates remain ordered by source priority.
```

### Example

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
P1 is rejected.
P2 is selected.
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
P1 is selected.
P2 is recorded as corroborating evidence.
```

In this policy, a higher extraction confidence from a lower-priority source does not automatically override a valid higher-priority source.

### Confidence Reporting

In this option, confidence can still be reported separately from the decision.

For example:

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

The important difference is that `conflict_score` is used for reporting and manual review decisions, not for choosing the value.

More precisely, conflict contributes to the floor check, so a high-priority candidate with poor agreement can fail the floor. However, conflict does not reorder candidates that already pass the floor. Priority still decides which passing candidate is selected first.

### Advantages

```text
1. Simple and explainable.
   The system uses the highest-priority acceptable source.

2. Conservative.
   Official or more trusted sources are preferred when they meet the minimum extraction confidence.

3. Easier to validate.
   If a result is unexpected, the client can inspect the priority order, two-part confidence, and confidence_floor.

4. Operationally stable.
   The behaviour is easier to debug because priority ordering and the confidence floor are separated.
```

### Disadvantages

```text
1. Less flexible than full final-score selection.
   A high-priority source can still be selected before a lower-priority source if both pass the floor.

2. Conflict affects eligibility but not ordering.
   A bad conflict score can make a candidate fail the floor, but conflict does not reorder candidates that pass the floor.

3. Strong dependency on priority configuration.
   If the priority labels in matching_rules.yaml are wrong, the matcher will consistently prefer the wrong source.

4. The confidence_floor and two-part confidence weights still need tuning.
   If the floor is too low, weak high-priority facts may pass.
   If the floor is too high, usable facts may be rejected.
```

## Common Rules For Both Options

Regardless of which selection policy is chosen, the following rules should apply.

### Object Scope Must Be Respected

Some MAPEM fields are not global fields. They belong to a specific object instance.

Examples:

```text
laneSet[].laneAttributes.laneType
```

This is a field for each lane, not one field for the whole junction.

```text
laneSet[].connectsTo[].signalGroup
```

This is a field for each lane connection, not one field for all signal groups.

Therefore, candidates must be grouped by:

```text
target_path + object_scope
```

Object scope can include:

```text
intersection_ref
lane_ref
connection_ref
node_ref
```

Candidates from different lanes or different connections must not be compared as if they describe the same field.

### Confidence And Decision Should Be Separate

Confidence explains how reliable the selected value appears to be.

Decision explains what the matcher decided to do with the value.

Example:

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

This separation is important because a value may be selected but still require review.

### High-Priority Conflicts Must Be Exposed

If a P1 candidate conflicts with several P1 or P2 candidates, the matcher should not hide that conflict.

Depending on the selected policy, the system may still choose the P1 candidate, but the decision status should show that manual review is needed.

Example statuses:

```text
matched
matched_with_conflict
manual_review_required
unresolved
pending_transform
```

### Provenance Must Be Preserved

Every selected value must be traceable back to the facts that produced it.

Each mapped evidence record should preserve:

```text
fact_id
fact_name
source_file
evidence_location
confidence
payload
```

### Corroborating And Rejected Evidence Should Be Kept

The matcher should not only output the selected value.

It should also record:

```text
corroborating facts
rejected facts
rejection reason
conflict details
priority used
priority spread
```

This makes the system auditable and helps manual review.

## Client Decision Question

The client can choose between two operating principles:

```text
Option A:
Should the matcher behave like an evidence-fusion engine, where source priority,
extraction confidence, and cross-source agreement jointly decide the selected value?
```

```text
Option B:
Should the matcher behave like a conservative priority-based mapper, where the
highest-priority acceptable source is selected after passing a two-part confidence
floor based on extraction confidence and conflict agreement?
```
