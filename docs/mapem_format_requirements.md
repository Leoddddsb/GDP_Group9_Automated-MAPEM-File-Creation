# MAPEM Format Requirements Notes

These notes summarise the MAPEM data format requirements relevant to this project, based on the project brief, client briefing slides, and the C-ITS European Handbook for MAPEM/SPATEM Creation v3.2.0.

## Project Interpretation

The project needs to generate machine-readable MAPEM topographic data for signal-controlled sites.

There are two output-format expectations in the current materials:

- The project brief asks for valid MAPEM files in ASN.1 format.
- The client briefing describes the task as extracting topographic content into a MAPEM file in JSON.

For this project, the safest interpretation is:

- Use JSON internally and for readable inspection.
- Generate `mapem.json` as a transparent project/debug output.
- Generate `mapem.asn1` as the standards-facing output.
- Generate `validation_report.json` to explain whether the MAPEM is complete, consistent, and accurate.

## MAPEM Concept

MAPEM describes the static topology of a road intersection or signal-controlled site. It does not describe signal timing or sequencing.

MAPEM should represent:

- intersection reference point
- lane geometry
- ingress and egress approaches
- permitted lane movements
- lane-to-lane connections
- signal group references
- optional signal head locations
- optional restrictions and speed limits

SPATEM is the related message for signal phase and timing. MAPEM and SPATEM need consistent intersection IDs and revision numbers, but SPATEM generation is out of scope for the current prototype.

## Top-Level Structure

The main MAPEM data frame is `MapData`.

Relevant `MapData` fields for this project:

| Field | Purpose | Project handling |
| --- | --- | --- |
| `timestamp` | Message timestamp | Optional for MVP |
| `msgIssueRevision` | MAPEM revision/version number | Required for version tracking |
| `layerType` | MAPEM fragmentation/layering | Only needed for fragmented messages |
| `layerID` | Fragment ID when one MAPEM is split across layers | Omit for MVP unless message is fragmented |
| `intersections` | List of `IntersectionGeometry` objects | Required |
| `roadSegments` | Road segments outside intersections | Out of MVP scope |
| `dataParameters` | Metadata about process/method/agency | Optional documentation field |
| `restrictionList` | Road user restrictions | Optional unless restrictions are known |
| `regional.signalHeadLocations` | Signal head location extension | Useful if signal head positions are extracted |

For most project sites, we should generate one `MapData` containing one `IntersectionGeometry`.

## IntersectionGeometry

`IntersectionGeometry` describes one signal-controlled site.

Relevant fields:

| Field | Purpose | Requirement |
| --- | --- | --- |
| `name` | Human-readable site name | Optional; handbook recommends omitting to reduce message size |
| `id.region` | Region/authority identifier | Needed for real deployment; MVP can use a documented placeholder |
| `id.id` | Intersection/site identifier | Required; must match related SPATEM if SPATEM exists |
| `revision` | Intersection topology version | Required |
| `refPoint.lat` | Reference latitude | Required |
| `refPoint.lon` | Reference longitude | Required |
| `refPoint.elevation` | Reference elevation | Optional for MVP |
| `laneWidth` | Generic lane width | Recommended; useful when per-node width is not encoded |
| `speedLimits` | Regulatory speed limits | Optional for MVP |
| `laneSet` | List of lanes at the intersection | Required |

The reference point should be near the centre of the intersection conflict area. Other geometry is encoded relative to this reference point, so a sensible `refPoint` keeps node offsets smaller and improves message efficiency.

## GenericLane

Each lane in `laneSet` is a `GenericLane`.

Relevant fields:

| Field | Purpose | Requirement |
| --- | --- | --- |
| `laneID` | Unique lane identifier inside the intersection | Required |
| `name` | Human-readable lane name | Optional |
| `ingressApproach` | Approach ID for entering lanes | Required for ingress lanes |
| `egressApproach` | Approach ID for exiting lanes | Required for egress lanes |
| `laneAttributes.directionalUse` | Ingress/egress/bidirectional use | Required where known |
| `laneAttributes.sharedWith` | Shared use, e.g. bicycle/pedestrian/tram | Required where relevant |
| `laneAttributes.laneType` | Vehicle, crosswalk, bike lane, sidewalk, etc. | Required |
| `maneuvers` | Allowed movements, e.g. left/straight/right | Required for controlled vehicle lanes |
| `nodeList` | Lane geometry as node points | Required |
| `connectsTo` | Downstream lane connections | Required for ingress lanes where known |
| `overlays` | Relationship to another lane | Optional |

The handbook states that `laneSet` should include all traffic-light-controlled lanes. Omitting controlled bicycle, pedestrian, or tracked-vehicle lanes can make the MAPEM misleading, because a receiver cannot know whether the lane does not exist or was merely omitted.

## Approaches

Each lane belongs to an approach.

Project interpretation:

- Ingress lanes enter the intersection.
- Egress lanes leave the intersection.
- Ingress and egress lanes on the same arm should share the same approach ID.
- Approach IDs should be consistent within the site and stable across revisions.

The current `SiteModel` has `approach_id` and `direction`; later schema revisions should map these explicitly to `ingressApproach` and `egressApproach`.

## NodeList And Geometry

`nodeList` describes lane geometry.

Relevant requirements:

- Nodes should represent the lane centreline.
- Node coordinates are relative to the intersection `refPoint`.
- Nodes should be accurate enough to describe the lane shape without making the message unnecessarily large.
- Fewer nodes are preferred when the lane shape can still be represented within quality limits.
- Extra attributes such as lane width delta and elevation delta can be added later if needed.

For this project, the minimum useful lane geometry is:

```json
{
  "lane_id": 1,
  "centerline": [[0.0, -40.0], [0.0, -10.0], [0.0, 0.0]]
}
```

These coordinates should be treated as local offsets from `refPoint`, not raw CAD coordinates.

## ConnectsTo

`connectsTo` describes which lane or lanes a vehicle can enter after following an ingress lane.

Relevant fields:

| Field | Purpose |
| --- | --- |
| `connectingLane.lane` | Target lane ID |
| `connectingLane.maneuver` | Movement used for the connection |
| `signalGroup` | Signal group controlling this connection |
| `connectionID` | Optional unique connection ID |
| `remoteIntersection` | Optional for connections into another intersection |

For MVP, the most important parts are:

- source lane ID
- target lane ID
- movement type
- signal group ID

## Signal Groups

MAPEM does not encode signal timing, but it references signal groups so that MAPEM topology can line up with SPATEM signal status.

For this project, each signal group should capture:

- numeric `signalGroupID`
- source phase label from the PDF, e.g. `A`, `B`, `C`
- controlled lanes or controlled lane connections
- description of the movement, if available

The PDF specification files are likely to be the main source for phase labels, movement descriptions, conflict matrices, and stage/phase relationships.

## Signal Head Locations

The handbook includes `signalHeadLocations` as a regional extension.

Relevant fields:

- `nodeXY`
- `nodeZ`
- `signalGroupID`

For this project, signal head locations are useful for quality assessment and richer MAPEM output, but they should be treated as optional until CAD/PDF extraction is reliable.

## Restrictions And Speed Limits

MAPEM can include:

- `restrictionList`
- road user types
- regulatory speed limits

These are useful but not essential for the first MVP. They should be added only when the source data clearly provides them.

## Minimum Viable MAPEM For This Project

A minimum useful MAPEM output should include:

- `MapData.msgIssueRevision`
- one `IntersectionGeometry`
- `IntersectionGeometry.id`
- `IntersectionGeometry.revision`
- `IntersectionGeometry.refPoint.lat`
- `IntersectionGeometry.refPoint.lon`
- `IntersectionGeometry.laneWidth`
- `IntersectionGeometry.laneSet`
- each lane's `laneID`
- each lane's ingress/egress approach
- each lane's lane type
- each lane's `nodeList`
- ingress lane `maneuvers`
- ingress lane `connectsTo`
- signal group references for controlled movements

## Data Source Mapping

| MAPEM requirement | Likely source |
| --- | --- |
| Site ID / intersection ID | Site folder name, PDF title, client metadata |
| `refPoint` | CAD/GIS coordinates, manually selected conflict-area centre |
| Lane geometry / `nodeList` | DWG/DXF geometry, GIS, manual correction |
| Lane type | CAD layers, road markings, PDF site map, manual interpretation |
| Stop lines | DWG/DXF geometry, PDF site map |
| Maneuvers | PDF stage arrows, phase descriptions, road markings |
| `connectsTo` | Lane geometry plus movement interpretation |
| Signal groups | PDF phase tables and signal labels |
| Signal head locations | CAD symbols, PDF site map, CV extraction |
| Restrictions | PDF notes, road markings, site specification |
| Speed limits | PDF notes, public GIS/OSM, manual entry |

## Current SiteModel Gap Analysis

The current repository `SiteModel` covers the first MVP shape, but it is not yet a complete MAPEM model.

Already covered:

- site ID
- site name
- revision
- reference point
- generic lane width
- lane ID
- lane type
- approach ID
- lane direction
- lane centreline
- maneuvers
- lane-to-lane connections
- signal group ID and phase label

Still missing or simplified:

- explicit `ingressApproach` vs `egressApproach`
- full `laneAttributes`
- per-node MAPEM delta type and coordinate encoding
- lane width deltas
- elevation
- connection-level signal groups and maneuvers
- signal head locations
- restriction list
- speed limits
- data parameters
- ASN.1 field names and encoding details beyond the current placeholder generator

## Validation Requirements

The validator should eventually check:

- every lane ID is unique
- every `connectsTo` target exists
- every signal group reference exists
- every lane has a non-empty `nodeList`
- ingress lanes have maneuvers or an explicit reason why not
- controlled lanes map to signal groups
- `refPoint` is present and plausible
- node offsets are within a plausible distance from the reference point
- generated MAPEM JSON and ASN.1 represent the same site content
- manual interventions are recorded

## Recommended Next Schema Updates

The next `SiteModel` version should add:

- `approaches`
- explicit `ingress_approach` and `egress_approach`
- `lane_attributes`
- connection objects instead of bare target lane IDs
- `signal_head_locations`
- optional `speed_limits`
- optional `restrictions`
- source provenance fields for each extracted element

This will make the intermediate JSON closer to real MAPEM while still staying practical for CAD/PDF/GIS extraction.

