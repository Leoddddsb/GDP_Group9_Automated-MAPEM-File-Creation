# MAPEM Completeness Scoring Mechanism

## 1. Introduction

This document defines a practical completeness scoring mechanism for evaluating automatically generated MAPEM outputs. The goal is to measure how completely a generated MAPEM captures the expected objects, fields, geometry, and semantic attributes that should exist in an ideal, fully populated reference MAPEM.

The mechanism evaluates **completeness**, not full correctness. Completeness asks:

> Has the generated MAPEM produced the expected information, and is that information meaningfully populated?

This is different from:

- generation success;
- ASN.1 data type validity;
- geometric accuracy;
- semantic correctness;
- safety validation;
- downstream application performance.

A MAPEM can be generated successfully and still be incomplete if lanes are missing, connections are absent, geometry is under-populated, or many fields are `null`, `unknown`, placeholder, or default fallback values.

## 2. Evaluation Objective

The scoring mechanism compares two MAPEM outputs:

- **Reference MAPEM**: a manually built or manually verified fully populated MAPEM for the selected site.
- **Generated MAPEM**: the automated MAPEM output produced by the generation pipeline.

The score should answer:

- Are all expected MAPEM objects generated?
- Are the expected fields present under those objects?
- Are field values meaningful rather than null, placeholder, or default fallback values?
- Which part of the generated MAPEM is incomplete?
- Does a new extraction, matching, fusion, or validation strategy improve completeness?

The output should include both a final score and diagnostic information so that the score can be traced back to missing objects, missing fields, null values, placeholders, or default values.

## 3. Reference MAPEM

Completeness scoring should be reference-based. A fully populated MAPEM should be prepared for a simple and well-defined site, such as a pedestrian crossing or a small intersection. This reference MAPEM acts as the expected output.

The reference MAPEM should define:

- expected intersection or node information;
- expected lane objects;
- expected lane geometry;
- expected lane-to-lane connections;
- expected maneuver information;
- expected pedestrian crossing, stop line, bicycle lane, vehicle lane, and other scenario-specific attributes;
- which fields are mandatory, scenario-specific, optional, or not applicable.

The reference MAPEM does not need to include every possible MAPEM feature. It only needs to be complete enough for the selected evaluation scenario.

## 4. Scoring Objects

The mechanism checks the following object groups:

| Object Group | What It Checks |
|---|---|
| MAPEM structure / schema | Whether the basic MAPEM container and hierarchy exist. |
| Intersection / node | Whether the mapped site context is populated. |
| Lane objects | Whether expected lanes are generated and populated. |
| Connection / maneuver | Whether lane-to-lane movement relationships are represented. |
| Geometry | Whether node lists, offsets, lane geometry, stop lines, and crossing geometry exist. |
| Semantic / scenario-specific attributes | Whether pedestrian crossing, stop line, lane use, and other scenario-specific attributes are populated. |
| Null / placeholder / default value diagnosis | Whether fields exist but contain non-meaningful values. |

The revised Excel template calculates a diagnostic score for each category. Every category uses the same three components: object coverage, field completeness, and value validity. Category scores are used to explain where completeness is lost; they are not assigned additional category weights and are not averaged to produce the overall score.

## 5. Scoring Granularity

The scoring mechanism uses five conceptual levels of granularity:

| Level | Meaning | Use |
|---|---|---|
| Field-level | Checks whether an individual field exists and has a meaningful value. | Finds missing, null, placeholder, or default values. |
| Object-level | Checks whether a lane, connection, crossing, stop line, or geometry object exists. | Locates missing objects. |
| Component-level | Aggregates object coverage, field completeness, and value validity. | Shows the type of completeness failure. |
| Category-level | Calculates the three component scores separately for structure, lanes, lane geometry, connections, other geometry, and semantics. | Shows which MAPEM subsystem causes the low score. |
| Overall-level | Produces one final 0-100 completeness score. | Supports reporting and comparison across experiments. |

Granularity matters because a single final score cannot explain why MAPEM generation is incomplete. The component scores and diagnostics make the final score interpretable.

## 6. Practical Scoring Formula

The Excel template uses a simplified three-component score:

```text
Overall Completeness Score =
  Object Coverage Score * Object Coverage Weight
+ Field Completeness Score * Field Completeness Weight
+ Value Validity Score * Value Validity Weight
```

Recommended first-version weights:

| Component | Weight | Meaning | Rationale |
|---|---:|---|---|
| Object Coverage Score | 40% | Whether expected MAPEM objects were generated. | Missing objects are the most severe completeness failure. |
| Field Completeness Score | 35% | Whether expected fields are present. | Captures whether generated objects are actually populated. |
| Value Validity Score | 25% | Whether present fields have meaningful values. | Captures null, placeholder, and default fallback problems. |
| **Total** | **100%** |  | Weights must sum to 1.00. |

These weights can be adjusted, but the first version should remain simple and explainable.

## 7. Field Importance Weights

Fields can have different importance levels:

| Field Importance | Weight | Meaning | Example |
|---|---:|---|---|
| Mandatory | 1.00 | Required by the MAPEM profile or essential for the evaluation. | `laneID`, `nodeList`, `connectsTo` |
| Scenario-specific | 0.70 | Important for the selected use case, even if not always mandatory. | `crossingGeometry`, `stopLineGeometry` |
| Optional | 0.30 | Useful but not central to the completeness objective. | descriptive name or non-critical attribute |
| Not applicable | 0.00 | Not expected in this scenario. | irrelevant fields |

The same field weight is used in both field completeness and value validity calculations.

## 8. Excel Template Structure

The revised Excel template contains six sheets:

| Sheet | Purpose |
|---|---|
| `Intro` | Explains the purpose, scope, scoring model, and workflow. |
| `README` | Explains how to use the workbook. |
| `Scoring_Config` | Defines component weights and field importance weights. |
| `Object_and_Field_Check` | Main working sheet where expected objects and fields are checked. |
| `Summary` | Aggregates scores and diagnostics. |
| `Category_Breakdown` | Calculates object coverage, field completeness, value validity, and a category score for each MAPEM category. |

The main data entry happens in `Object_and_Field_Check`. The `Summary` and `Category_Breakdown` sheets read the helper columns from that sheet and calculate their results automatically. Adding category breakdown therefore does not require a second manual scoring process.

## 9. Object_and_Field_Check Columns

Each row in `Object_and_Field_Check` represents:

```text
one expected field under one expected MAPEM object
```

For example:

```text
Object: LANE-001
Field: laneWidth
```

| Column | Meaning | Filled By |
|---|---|---|
| `Object ID` | Evaluation ID for an expected object. This is not necessarily a native MAPEM field. | User |
| `Object Category` | Broad object group, such as lane, connection, geometry, or semantic object. | User |
| `Object Type` | Specific object type, such as vehicle lane or pedestrian crossing. | User |
| `Object Description` | Human-readable description of the object. | User |
| `Generated?` | Whether the object exists in the generated MAPEM. | User |
| `Field Name` | MAPEM field being checked. | User |
| `Field Importance` | Mandatory, scenario-specific, optional, or not applicable. | User |
| `Field Weight` | Numeric weight from `Scoring_Config`. | User |
| `Field Present?` | Whether this field exists in the generated MAPEM. | User |
| `Value Status` | Whether the value is complete, missing, null, placeholder, default, or not applicable. | User |
| `Object Expected Unit` | Counts each unique expected object once. | Formula |
| `Object Generated Unit` | Counts each generated object once. | Formula |
| `Field Completeness Unit` | Weighted field presence score for this row. | Formula |
| `Value Validity Unit` | Weighted meaningful-value score for this row. | Formula |
| `Notes` | Explanation or comments. | User |

The `Object Category` values should use the following exact labels so that the `SUMIFS` formulas in `Category_Breakdown` can group the rows correctly:

```text
Structure / Schema
Intersection / Node
Lane Object
Lane Geometry
Connection / Maneuver
Other Geometry
Semantic / Scenario-Specific
```

## 10. Helper Column Formulas

### 10.1 Object Expected Unit

Purpose:

```text
Count each unique expected object once.
```

Formula:

```excel
=IF(A2="","",IF(COUNTIF($A$2:A2,A2)=1,1,0))
```

Logic:

- If this is the first row where the `Object ID` appears, the value is `1`.
- If the object has already appeared in a previous row, the value is `0`.

Example:

| Object ID | Field Name | Object Expected Unit |
|---|---|---:|
| `LANE-001` | `laneID` | 1 |
| `LANE-001` | `laneWidth` | 0 |
| `LANE-001` | `nodeList` | 0 |
| `LANE-002` | `laneID` | 1 |

### 10.2 Object Generated Unit

Purpose:

```text
Count each generated expected object once.
```

Formula:

```excel
=IF(K2=1,IF(COUNTIFS($A$2:$A$200,A2,$E$2:$E$200,"Yes")>0,1,0),0)
```

Logic:

- Only the first row of each object can receive a generated-object score.
- If any row with the same `Object ID` has `Generated? = Yes`, the object is counted as generated.

### 10.3 Field Completeness Unit

Purpose:

```text
Give weighted credit when an expected field is present.
```

Formula:

```excel
=H2*IF(I2="Yes",1,0)
```

Logic:

- If `Field Present? = Yes`, the field receives its `Field Weight`.
- If `Field Present? = No`, the field receives `0`.

### 10.4 Value Validity Unit

Purpose:

```text
Give weighted credit only when the field value is meaningful.
```

Formula:

```excel
=H2*IF(J2="Complete",1,0)
```

Logic:

- If `Value Status = Complete`, the field receives its `Field Weight`.
- If the value is `Missing`, `Null`, `Placeholder`, or `Default`, the field receives `0`.

This distinction prevents a generated MAPEM from receiving high completeness simply because fields exist while their values are empty or meaningless.

## 11. Summary Sheet

The `Summary` sheet is the final aggregation sheet. It reads helper columns from `Object_and_Field_Check`.

### 11.1 Summary Column Titles

| Column Title | Meaning |
|---|---|
| `Metric` | The name of the metric being calculated. |
| `Formula / Value` | The raw formula result, such as a count, weight sum, or 0-1 score. |
| `Score` | Percentage display of a 0-1 score. |
| `Interpretation` | Text interpretation of a score or configuration status. |
| `Notes` | Explanation of where the metric comes from. |

### 11.2 Summary Metric Calculations

| Metric | Meaning | Formula / Logic | Example |
|---|---|---|---:|
| `Total expected objects` | Unique expected objects in the reference MAPEM. | `SUM(Object Expected Unit)` | `8` |
| `Generated objects` | Unique expected objects generated by the automated MAPEM. | `SUM(Object Generated Unit)` | `5` |
| `Object Coverage Score` | Generated object ratio. | `Generated objects / Total expected objects` | `5 / 8 = 62.50%` |
| `Total expected field weight` | Weighted total of all expected fields. | `SUM(Field Weight)` | `14.50` |
| `Present field weight` | Weighted total of fields that are present. | `SUM(Field Completeness Unit)` | `9.40` |
| `Field Completeness Score` | Weighted field presence ratio. | `Present field weight / Total expected field weight` | `64.83%` |
| `Meaningful value weight` | Weighted total of fields with meaningful values. | `SUM(Value Validity Unit)` | `7.70` |
| `Value Validity Score` | Weighted meaningful-value ratio. | `Meaningful value weight / Total expected field weight` | `53.10%` |
| `Overall Completeness Score` | Final weighted completeness score. | `Object Coverage * 0.40 + Field Completeness * 0.35 + Value Validity * 0.25` | `60.97%` |
| `Missing values` | Number of fields marked `Missing`. | `COUNTIF(Value Status, "Missing")` | from table |
| `Null values` | Number of fields marked `Null`. | `COUNTIF(Value Status, "Null")` | from table |
| `Placeholder values` | Number of fields marked `Placeholder`. | `COUNTIF(Value Status, "Placeholder")` | from table |
| `Default fallback values` | Number of fields marked `Default`. | `COUNTIF(Value Status, "Default")` | from table |
| `Objects not generated` | Expected objects that were not generated. | `Total expected objects - Generated objects` | `8 - 5 = 3` |
| `Config weight check` | Checks whether weights sum to 1.00. | `Scoring_Config total weight` | `1.00` |

## 12. Category Breakdown

### 12.1 Purpose

The `Category_Breakdown` sheet adds diagnostic detail without changing the main scoring model. It answers questions such as:

- Is the main weakness missing lane objects?
- Are lane objects present but lane geometry incomplete?
- Are connection and maneuver relationships missing?
- Are geometry fields present but filled with default values?
- Are pedestrian or other scenario-specific semantics absent?

The category breakdown uses data already entered in `Object_and_Field_Check`. No additional manual category scoring is required.

### 12.2 Category Definitions

| Category | Included Content |
|---|---|
| `Structure / Schema` | MAPEM container, message frame, map data hierarchy, and basic structural fields. |
| `Intersection / Node` | Intersection ID, revision, reference point, node context, and related fields. |
| `Lane Object` | Lane existence, lane ID, lane width, lane type, lane attributes, and other non-geometric lane fields. |
| `Lane Geometry` | Lane node lists, node offsets, lane shape representation, and lane-specific geometry fields. |
| `Connection / Maneuver` | `connectsTo`, target lane relationships, maneuvers, and movement mappings. |
| `Other Geometry` | Stop-line geometry and other geometry that is not represented as lane geometry. |
| `Semantic / Scenario-Specific` | Pedestrian, bicycle, crossing type, lane-use, and other use-case-specific semantic information. |

The categories can be extended later, but the labels used in `Object_and_Field_Check` must match the labels in `Category_Breakdown`.

### 12.3 Category_Breakdown Column Titles

| Column | Meaning |
|---|---|
| `Category` | The MAPEM category being evaluated. |
| `Expected Objects` | Number of unique expected objects assigned to this category. |
| `Generated Objects` | Number of unique expected objects in this category that were generated. |
| `Object Coverage` | Generated objects divided by expected objects for this category. |
| `Expected Field Weight` | Sum of field weights for all expected fields in this category. |
| `Present Field Weight` | Sum of field completeness units in this category. |
| `Field Completeness` | Present field weight divided by expected field weight. |
| `Meaningful Value Weight` | Sum of value validity units in this category. |
| `Value Validity` | Meaningful value weight divided by expected field weight. |
| `Category Score` | Weighted combination of category object coverage, field completeness, and value validity. |
| `Interpretation` | Text interpretation of the category score. |

### 12.4 Category Aggregation with SUMIFS

Each category row uses `SUMIFS` to include only rows whose `Object Category` matches the category name in column A.

For the first category row, `Structure / Schema`, the formulas are:

#### Expected Objects

```excel
=SUMIFS(
  Object_and_Field_Check!$K$2:$K$200,
  Object_and_Field_Check!$B$2:$B$200,
  $A2
)
```

Meaning:

- Column K contains `Object Expected Unit`.
- Column B contains `Object Category`.
- `$A2` contains the category name.
- The formula sums only expected-object units assigned to that category.

#### Generated Objects

```excel
=SUMIFS(
  Object_and_Field_Check!$L$2:$L$200,
  Object_and_Field_Check!$B$2:$B$200,
  $A2
)
```

Meaning:

- Column L contains `Object Generated Unit`.
- The formula counts generated unique objects within the selected category.

#### Object Coverage

```excel
=IF(B2=0,"",C2/B2)
```

Meaning:

```text
Category Object Coverage =
Category Generated Objects / Category Expected Objects
```

If a category contains no expected objects, the cell is left blank instead of producing a division error.

#### Expected Field Weight

```excel
=SUMIFS(
  Object_and_Field_Check!$H$2:$H$200,
  Object_and_Field_Check!$B$2:$B$200,
  $A2
)
```

Meaning:

- Column H contains `Field Weight`.
- The formula sums the weights of all expected fields assigned to the category.

#### Present Field Weight

```excel
=SUMIFS(
  Object_and_Field_Check!$M$2:$M$200,
  Object_and_Field_Check!$B$2:$B$200,
  $A2
)
```

Meaning:

- Column M contains `Field Completeness Unit`.
- Only fields marked `Field Present? = Yes` contribute their field weight.

#### Field Completeness

```excel
=IF(E2=0,"",F2/E2)
```

Meaning:

```text
Category Field Completeness =
Category Present Field Weight / Category Expected Field Weight
```

#### Meaningful Value Weight

```excel
=SUMIFS(
  Object_and_Field_Check!$N$2:$N$200,
  Object_and_Field_Check!$B$2:$B$200,
  $A2
)
```

Meaning:

- Column N contains `Value Validity Unit`.
- Only fields marked `Value Status = Complete` contribute their field weight.

#### Value Validity

```excel
=IF(E2=0,"",H2/E2)
```

Meaning:

```text
Category Value Validity =
Category Meaningful Value Weight / Category Expected Field Weight
```

#### Category Score

```excel
=IF(
  OR(B2=0,E2=0),
  "",
  D2*Scoring_Config!$B$2
  +G2*Scoring_Config!$B$3
  +I2*Scoring_Config!$B$4
)
```

Meaning:

```text
Category Score =
  Category Object Coverage * 40%
+ Category Field Completeness * 35%
+ Category Value Validity * 25%
```

The formula checks `Expected Objects` and `Expected Field Weight` to distinguish a real category score of zero from a category with no evaluation data.

### 12.5 Category Interpretation Formula

```excel
=IF(
  OR(B2=0,E2=0),
  "No data",
  IF(J2>=0.9,"Very complete",
  IF(J2>=0.75,"Mostly complete",
  IF(J2>=0.6,"Partially complete",
  IF(J2>=0.4,"Low completeness",
  "Very incomplete"))))
)
```

Interpretation thresholds:

| Category Score | Interpretation |
|---:|---|
| 90-100% | Very complete |
| 75-89.99% | Mostly complete |
| 60-74.99% | Partially complete |
| 40-59.99% | Low completeness |
| 0-39.99% | Very incomplete |
| No expected object or field data | No data |

### 12.6 Worked Category Examples

#### Structure / Schema

Example values:

```text
Expected Objects = 1
Generated Objects = 1
Object Coverage = 1 / 1 = 100%

Expected Field Weight = 2.00
Present Field Weight = 2.00
Field Completeness = 2.00 / 2.00 = 100%

Meaningful Value Weight = 2.00
Value Validity = 2.00 / 2.00 = 100%
```

```text
Category Score =
100% * 40% + 100% * 35% + 100% * 25%
= 100%
```

Interpretation: `Very complete`.

#### Lane Object

Example values:

```text
Expected Objects = 2
Generated Objects = 1
Object Coverage = 1 / 2 = 50.00%

Expected Field Weight = 4.70
Present Field Weight = 2.70
Field Completeness = 2.70 / 4.70 = 57.45%

Meaningful Value Weight = 1.70
Value Validity = 1.70 / 4.70 = 36.17%
```

```text
Lane Object Category Score =
50.00% * 40%
+ 57.45% * 35%
+ 36.17% * 25%

= 20.00%
+ 20.11%
+ 9.04%

= 49.15%
```

Interpretation: `Low completeness`.

This result shows that lane completeness is reduced by:

- one missing lane object;
- missing fields under the missing lane;
- a `Null` value for `laneWidth`.

#### Lane Geometry

Example values:

```text
Expected Objects = 1
Generated Objects = 1
Object Coverage = 100%
Field Completeness = 100%
Value Validity = 100%
Category Score = 100%
```

Interpretation: `Very complete`.

This indicates that the example lane geometry object, `nodeList`, and `offsetPoints` are all present and meaningfully populated. It does not prove that the geometric coordinates are accurate; coordinate accuracy belongs to a separate geometry accuracy metric.

#### Connection / Maneuver

Example values:

```text
Expected Objects = 1
Generated Objects = 0
Object Coverage = 0%

Expected Field Weight = 1.70
Present Field Weight = 0
Field Completeness = 0%

Meaningful Value Weight = 0
Value Validity = 0%

Category Score = 0%
```

Interpretation: `Very incomplete`.

This clearly identifies connection generation as a major weakness even when the overall score remains above zero.

#### Other Geometry

Example values:

```text
Expected Objects = 1
Generated Objects = 1
Object Coverage = 100%

Expected Field Weight = 0.70
Present Field Weight = 0.70
Field Completeness = 100%

Meaningful Value Weight = 0
Value Validity = 0%
```

```text
Other Geometry Category Score =
100% * 40% + 100% * 35% + 0% * 25%
= 75%
```

Interpretation: `Mostly complete`.

The object and field exist, but `stopLineGeometry` contains a default fallback value. This is why field completeness is high while value validity is zero.

#### Semantic / Scenario-Specific

Example values:

```text
Expected Objects = 1
Generated Objects = 0
Object Coverage = 0%
Field Completeness = 0%
Value Validity = 0%
Category Score = 0%
```

Interpretation: `Very incomplete`.

### 12.7 Relationship Between Overall and Category Scores

The overall score is calculated from all expected objects and fields pooled together:

```text
Overall Object Coverage =
Total generated objects / Total expected objects

Overall Field Completeness =
Total present field weight / Total expected field weight

Overall Value Validity =
Total meaningful value weight / Total expected field weight
```

The overall score is **not**:

```text
AVERAGE(all category scores)
```

This design prevents a small category containing one optional field from having the same influence as a large category containing many mandatory lane and connection fields.

Category scores are therefore diagnostic outputs. They show where completeness is strong or weak, while the overall score remains the principal cross-experiment comparison metric.

## 13. Example Overall Calculation

Using the example values in the template:

```text
Object Coverage Score = 62.50%
Field Completeness Score = 64.83%
Value Validity Score = 53.10%
```

With weights:

```text
Object Coverage Weight = 40%
Field Completeness Weight = 35%
Value Validity Weight = 25%
```

The final calculation is:

```text
Overall Completeness Score =
  62.50 * 0.40
+ 64.83 * 0.35
+ 53.10 * 0.25

= 25.00
+ 22.69
+ 13.28

= 60.97
```

Interpretation:

- `62.50%` means that 5 out of 8 expected objects were generated.
- `64.83%` means that around two thirds of expected weighted fields are present.
- `53.10%` means that slightly more than half of expected weighted fields contain meaningful values.
- The final score of `60.97%` indicates partial completeness. The category breakdown shows that connection and semantic generation are the main weaknesses.

## 14. Interpretation Scale

| Score Range | Interpretation |
|---|---|
| 90-100 | Very complete; only minor fields are missing. |
| 75-89 | Mostly complete; some category-level weaknesses remain. |
| 60-74 | Partially complete; important objects or fields are missing. |
| 40-59 | Low completeness; major information is missing. |
| 0-39 | Very incomplete; output is unreliable for downstream use. |

## 15. Limitations

This scoring mechanism evaluates completeness only. It does not replace:

- correctness evaluation;
- geometric accuracy evaluation;
- semantic accuracy evaluation;
- safety validation;
- downstream application testing.

For example, if `laneWidth` is populated with a value, completeness scoring can recognize that the field is present and meaningful. Whether the value is numerically correct should be evaluated by a separate correctness or accuracy metric.
