Automated MAPEM File Creation

This repository contains the code and supporting materials developed for the Imperial College London Group Design Project Automated MAPEM File Creation from UK Traffic Signal Site Data.

The project explores how existing traffic-signal site records, including CAD drawings, PDF signal plans, controller information and configuration files, can be processed into MAPEM-oriented outputs. The current implementation is a prototype workflow intended to support structured MAPEM generation, evidence tracing and review, rather than to replace manual MAPEM verification.

Project Aim

MAPEM describes the static geometry and topology of a signalised junction. It includes information such as the intersection reference point, lane layout, lane attributes, lane connections and signal-group relationships. This project investigates whether these elements can be derived from existing highway authority site data.

The main aims of the project are to:

* identify which source documents contain MAPEM-relevant information;
* extract candidate facts from heterogeneous site files;
* match extracted evidence to MAPEM-oriented fields;
* combine evidence from multiple sources through fusion;
* generate MAPEM-style JSON and ASN.1-style outputs;
* produce reports showing populated fields, gaps, conflicts and review items.

Repository Structure

The current repository is organised as follows:

.
├── .github/                              # GitHub workflows or repository configuration
├── configs/                              # Site and pipeline configuration files
├── data/                                 # Local data folder
├── docs/                                 # Project documentation and user guidance
├── notes/                                # Development notes and intermediate project notes
├── src/mapemgen/                         # Core MAPEM generation package
├── tests/                                # Tests and checking scripts
├── .gitattributes                        # Git LFS and repository attribute settings
├── .gitignore                            # Files and folders excluded from version control
├── MAPEM_Completeness_Scoring_Mechanism... # Completeness scoring document
├── README.md                             # Project README
├── pyproject.toml                        # Python project and package configuration
├── run_pipeline.py                       # Main pipeline runner
└── run_pipeline_with_generator.py        # Pipeline runner including generation stage

The main implementation is located in src/mapemgen/. The top-level runner scripts, run_pipeline.py and run_pipeline_with_generator.py, are used to execute the pipeline workflow. Configuration files are stored in configs/, while project documentation and supporting notes are kept in docs/ and notes/.

Pipeline Overview

The workflow is organised into several main stages:

1. Site inventory
    Records the source files available for each site.
2. Fact extraction
    Extracts MAPEM-relevant candidate facts from CAD, PDF, configuration and other available source files.
3. Geometry and semantic assignment
    Assigns extracted facts to relevant scopes, such as intersections, approaches, lanes, movements or signal groups where possible.
4. Evidence matching
    Maps scoped evidence to MAPEM-oriented target fields.
5. Fusion
    Combines evidence from different sources into a fused site model while recording gaps, conflicts and review items.
6. Output generation
    Produces MAPEM-style JSON and ASN.1-style output artefacts where generation is successful.
7. Validation and reporting
    Produces supporting reports for checking completeness, consistency and manual-review requirements.

How to Use

Detailed installation, environment setup and step-by-step execution instructions are provided in the project user guide:

docs/[v3.0] MAPEM Generation Pipeline - User Guide.pdf

Users should refer to the guide for:

* required dependencies;
* folder and input-data preparation;
* site configuration;
* running the pipeline;
* generated output files;
* known limitations;
* post-generation checks.

Outputs

The pipeline can produce several types of output artefacts:

* mapped evidence: records how extracted facts are linked to MAPEM-oriented fields;
* fused model: combines selected values into a structured site model;
* fusion report: records accepted fields, gaps, conflicts and manual-review items;
* MAPEM-style JSON: structured output for inspection and validation;
* ASN.1-style output: MAPEM-facing output prepared for the project requirement;
* validation report: records completeness and consistency checks.

These outputs should be treated as review artefacts and working drafts unless they have been manually checked and validated.

Testing and Example Sites

The workflow was tested on a set of UK traffic-signal sites with different levels of complexity, including pedestrian crossings, signalised junctions, signalised roundabouts and corridor-style sites.

Selected testing and reference cases include:

* 337L: signalised roundabout used for workflow testing and refinement;
* 397L: Toucan crossing with a manually populated MAPEM reference for comparison;
* 1084: Puffin crossing used as a manual reference case;
* 1003 and 1062: more complex signalised junction cases showing information-overload and convergence challenges.

Testing showed that the pipeline can generate structured MAPEM-oriented artefacts, but lane geometry, movement connections and signal semantics remain the main areas requiring further work.

Current Limitations

This repository represents a project prototype rather than a production MAPEM generator. The current system supports evidence extraction, field mapping, fusion and output review, but further development is needed before it could support complete MAPEM generation across different site types.

Key limitations include:

* incomplete lane geometry generation;
* unresolved or partial connectsTo relationships;
* incomplete signal-group association;
* limited handling of conflicting evidence;
* dependence on manual configuration and source-document quality;
* no operational safety validation.

Acknowledgement

This repository was developed as part of the Imperial College London Group Design Project by Group 9. The project was supported by Pleydell Technology Consulting Ltd. and supervised by staff from the Department of Civil and Environmental Engineering at Imperial College London.
