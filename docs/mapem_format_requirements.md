# MAPEM Data Structure Requirements

This document is a simplified project-facing explanation of the MAPEM data structure. It is not a full translation of the standard. Its purpose is to help the team understand:

- what the MAPEM hierarchy looks like
- what each layer contains
- where our extracted CAD/PDF/GIS data should fit
- how the current `SiteModel` example is shaped

## 1. Core MAPEM Data Structure

MAPEM can be understood as this tree:

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

The key relationship is:

```text
MapData
  -> IntersectionGeometry
      -> GenericLane
          -> nodeList       lane geometry
          -> connectsTo     lane connection relationship
              -> signalGroup    signal group controlling this connection
```

In plain terms:

- `MapData` is the whole MAPEM message.
- `IntersectionGeometry` is one junction or signal-controlled site.
- `GenericLane` is one lane inside that site.
- `nodeList` describes the lane geometry.
- `connectsTo` describes which downstream lane this lane can connect to.
- `signalGroup` sits under `connectsTo` and describes which signal group controls that lane connection / movement.

## 2. First Layer: MapData

`MapData` is the outer layer of MAPEM.

```text
MapData
|
+-- msgIssueRevision
+-- intersections
+-- restrictionList       optional
+-- dataParameters        optional
```

For this project, the most important fields are:

| Field | Meaning | Needed for MVP |
| --- | --- | --- |
| `msgIssueRevision` | MAPEM version / revision number | Yes |
| `intersections` | List of junctions | Yes |
| `restrictionList` | Restriction information | Optional |
| `dataParameters` | Generation method, agency, metadata | Optional |

For most project sites, we can start with:

```text
one MapData
  containing one IntersectionGeometry
```

## 3. Second Layer: IntersectionGeometry

`IntersectionGeometry` represents one specific junction or signal-controlled site.

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

Important fields:

- `id`: the site or junction ID.
- `revision`: the topology version of this site.
- `refPoint`: the reference point, usually near the centre of the conflict area.
- `laneWidth`: generic lane width.
- `laneSet`: all lanes encoded for this site.

| Field | Meaning | Likely source |
| --- | --- | --- |
| `id.region` | Region or road authority identifier | Client / manual setup |
| `id.id` | Junction/site identifier | Site ID, PDF title, folder name |
| `revision` | Site topology version | Manual setup or version management |
| `refPoint.lat` | Reference point latitude | GIS/CAD/manual selection |
| `refPoint.lon` | Reference point longitude | GIS/CAD/manual selection |
| `laneWidth` | Default lane width | CAD/PDF/default value |
| `laneSet` | Lane collection | CAD + PDF + manual checking |

`refPoint` is important because many MAPEM geometry points are encoded as offsets from it rather than as raw CAD coordinates.

## 4. Third Layer: GenericLane

`GenericLane` represents one lane.

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

| Field | Meaning | Likely source |
| --- | --- | --- |
| `laneID` | Unique lane ID | Auto-numbering / manual confirmation |
| `ingressApproach` | Ingress approach | Lane direction interpretation |
| `egressApproach` | Egress approach | Lane direction interpretation |
| `laneAttributes.laneType` | Lane type | CAD layers, PDF, manual interpretation |
| `laneAttributes.directionalUse` | Ingress/egress/bidirectional use | CAD/GIS/manual interpretation |
| `maneuvers` | Allowed left/straight/right movements | PDF phase/stage diagrams, road markings |
| `nodeList` | Lane centreline geometry | CAD/DXF/GIS |
| `connectsTo` | Downstream lane connections | Geometry + movement interpretation |

Simple interpretation:

```text
GenericLane = lane ID + type + direction + geometry + movement + connections
```

## 5. nodeList: Lane Geometry

`nodeList` describes the lane centreline.

```text
nodeList
|
+-- NodeXY 1
+-- NodeXY 2
+-- NodeXY 3
+-- ...
```

Each `NodeXY` is a point. Multiple points form the lane centreline.

```text
Lane centreline

Node 1 ------ Node 2 ------ Node 3
```

In our intermediate JSON, this can be represented as:

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

Notes:

- These points should be local offsets from `refPoint`.
- Do not directly place raw CAD coordinates into MAPEM.
- Too few nodes reduce geometry accuracy.
- Too many nodes increase message size.

## 6. connectsTo: Lane Connection Relationship

`connectsTo` describes where an ingress lane can go after entering the junction.

```text
GenericLane 1
|
+-- connectsTo
    |
    +-- connectingLane: Lane 2
    +-- maneuver: straight
    +-- signalGroup: 1
```

This can also be read as:

```text
Lane 1  --straight / signalGroup 1-->  Lane 2
```

For MVP, we need at least:

| Information | Example |
| --- | --- |
| Source lane | Lane 1 |
| Target lane | Lane 2 |
| Movement | straight / left / right |
| Signal group | Signal Group 1 |

This usually cannot be inferred from CAD alone. It often needs:

- PDF stage diagrams
- phase tables
- road markings
- manual checking

## 7. signalGroup: Signal Group

MAPEM does not describe signal timing, but it references signal groups so that MAPEM topology can line up with SPATEM signal state.

Conceptual structure:

```text
SignalGroup
|
+-- signalGroupID
+-- phaseLabel
+-- controlledLanes
+-- description
```

Example:

```text
SignalGroup 1
|
+-- phaseLabel: A
+-- controlledLanes: Lane 1
+-- description: northbound ahead movement
```

Likely PDF sources:

- USE OF PHASES
- STAGE / PHASE table
- CONFLICTING PHASES
- stage arrows
- phase labels such as A/B/C/D

## 8. signalHeadLocations: Optional Extension

If signal head locations can be extracted from CAD or PDF, they can be added:

```text
signalHeadLocations
|
+-- nodeXY
+-- nodeZ
+-- signalGroupID
```

This is useful for quality assessment, but it is not required for the first MVP.

## 9. Minimum Viable MAPEM For This Project

The first working MAPEM should include at least:

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

In other words, the MVP does not need to cover the whole MAPEM standard, but it must clearly answer:

1. Which junction is this?
2. Where is the reference point?
3. Which lanes exist?
4. What is the geometry of each lane?
5. What movements are allowed from each ingress lane?
6. Which egress lane does each ingress lane connect to?
7. Which signal group controls each movement?

## 10. Source Data To MAPEM Field Mapping

| MAPEM content | Main source |
| --- | --- |
| Junction ID | Folder name, PDF title, client metadata |
| `refPoint` | CAD/GIS coordinates, manual selection |
| lane geometry / `nodeList` | DWG/DXF, GIS |
| lane type | CAD layer, PDF site map, manual interpretation |
| stop line | DWG/DXF, PDF site map |
| maneuvers | PDF stage arrows, phase descriptions, road markings |
| connectsTo | Lane geometry + movement interpretation |
| signal groups | PDF phase tables, signal labels |
| signal head locations | CAD symbols, PDF drawings, CV |
| restrictions | PDF notes, road markings |
| speed limits | PDF, OSM/GIS, manual entry |

## 11. Current SiteModel As A MAPEM Example

The current `examples/site_model.example.json` file is a MAPEM-style example. It is not generated from real Leeds data. It shows the shape that extraction modules should eventually produce.

Current structure:

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
|           |   +-- elevation        optional
|           |
|           +-- laneWidth            optional but recommended
|           +-- speedLimits          optional
|           +-- signalHeadLocations  optional
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

Simplified JSON view:

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

## 12. Current SiteModel Coverage

| MAPEM content | Current field |
| --- | --- |
| MAPEM top level | `mapData` |
| MAPEM revision | `mapData.msgIssueRevision` |
| Junction list | `mapData.intersections` |
| Junction object | `IntersectionGeometry` |
| Junction ID | `IntersectionGeometry.id` |
| Junction revision | `IntersectionGeometry.revision` |
| Junction reference point | `IntersectionGeometry.refPoint` |
| Generic lane width | `IntersectionGeometry.laneWidth` |
| Lane collection | `IntersectionGeometry.laneSet` |
| Single lane | `GenericLane` |
| Lane attributes | `GenericLane.laneAttributes` |
| Lane geometry | `GenericLane.nodeList.nodes` |
| Lane movement | `GenericLane.maneuvers` |
| Lane connection | `GenericLane.connectsTo` |
| Connection target lane | `connectsTo.connectingLane.lane` |
| Connection movement | `connectsTo.connectingLane.maneuver` |
| Connection signal group | `connectsTo.signalGroup` |
| Signal head location | `IntersectionGeometry.signalHeadLocations` |
| Speed limits | `IntersectionGeometry.speedLimits` |
| Restrictions | `mapData.restrictionList` |
| Generation metadata | `mapData.dataParameters` |

## 13. Remaining Gaps Before Production-Grade MAPEM

The current `SiteModel` hierarchy is MAPEM-style, but it is still not a production-grade MAPEM encoder.

Still needed:

- stricter ASN.1 enumerations and bit string representation
- real MAPEM `NodeXY` delta type encoding
- lane width deltas
- fuller regional extension support
- source provenance for every extracted field
- stricter geometry quality checks, such as node spacing, offset range, and connection plausibility
- ASN.1 output that can be parsed by standards-compliant tools, not only the current ASN.1-style text representation

Recommended next addition:

```text
source provenance
|
+-- which CAD layer each lane came from
+-- which PDF table or stage diagram each movement came from
+-- which phase label each signalGroup came from
+-- which fields were manually checked
```

This will make `validation_report.json` able to explain:

- what was extracted automatically
- what was manually corrected
- what is missing or unreliable
