# eBOM → mBOM Data Transformation Platform

> **Enterprise-grade PLM/PDM data transformation engine for manufacturing BOM generation.**
>
> Built to demonstrate deep understanding of Product Data Management (PDM) and Product Lifecycle Management (PLM) systems, specifically the critical eBOM-to-mBOM conversion problem that every manufacturing organization faces.

---

## Table of Contents

1. [What is eBOM vs mBOM?](#what-is-ebom-vs-mbom)
2. [Why This Conversion is Hard](#why-this-conversion-is-hard)
3. [Architecture](#architecture)
4. [Project Structure](#project-structure)
5. [Core Features](#core-features)
6. [Transformation Rules](#transformation-rules)
7. [Running the Project](#running-the-project)
8. [API Reference](#api-reference)
9. [Testing](#testing)
10. [Interview Talking Points](#interview-talking-points)
11. [What I'd Do Differently at Enterprise Scale](#what-id-do-differently-at-enterprise-scale)

---

## What is eBOM vs mBOM?

### eBOM (Engineering Bill of Materials)

The eBOM is how a **designer** thinks about a product. It is:

- **Organized by function**: electrical sub-assemblies, mechanical sub-assemblies, software modules
- **Tied to 3D-CAD models**: every part has a CAD reference ID
- **Includes design-intent parts**: virtual parts (reference envelopes), reference geometry, tolerance annotations
- **Structured by design hierarchy**: parent-child relationships reflect design decomposition, not build sequence

**Example**: A wire harness assembly appears as a single line item because that's how the electrical engineer designed it.

### mBOM (Manufacturing Bill of Materials)

The mBOM is how the **factory floor** thinks about a product. It is:

- **Organized by build sequence**: operation 10, operation 20, operation 30...
- **Includes non-design items**: adhesives, packaging, calibration fluid, shop-floor consumables
- **Reflects actual assembly**: sub-assemblies are built and staged on specific work centers
- **May split or merge eBOM items**: one designed part becomes multiple purchased items; multiple design fasteners become one kit

**Example**: That same wire harness explodes into wire, crimp terminals, and heat-shrink tubing — each with its own supplier lead time and work center assignment.

### The Conversion Problem

| eBOM Item | mBOM Fate | Why |
|-----------|-----------|-----|
| Virtual reference envelope | **Excluded** | No physical part to manufacture or buy |
| Wire harness assembly | **Split** into wire + connector + heat-shrink | Procurement buys individual items |
| 4 individual M3 screws | **Merged** into "M3 Fastener Kit" | Kitting reduces line-side inventory |
| (doesn't exist in eBOM) | **Added**: thermal paste, packaging | Manufacturing needs consumables |
| 1.0m wire per assembly | **Requantified** to 1.08m | 8% scrap during cutting/stripping |

This is a **many-to-many, rule-driven remapping** — and it is the actual hard part of PLM/PDM implementation.

---

## Why This Conversion is Hard

1. **Not 1:1 mapping**: An eBOM line can produce zero, one, or many mBOM lines. An mBOM line can consume multiple eBOM lines.

2. **Rules are context-dependent**: "Add thermal paste" only applies when a motor is present. "Split harness" only applies to harness assemblies.

3. **Quantities change for production reality**: Scrap rates, batch sizing, and yield factors mean the eBOM quantity is rarely the mBOM quantity.

4. **Traceability is mandatory**: Manufacturing engineers need to know **why** the mBOM looks the way it does. "Where did this line come from?" is not optional.

5. **Unmapped parts must be flagged, not dropped**: Silently dropping a part that no rule matched is a production-stopping bug. Real PLM systems queue these for human review.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         eBOM → mBOM Platform                             │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────────┐    ┌─────────────────────────┐  │
│  │   eBOM      │───▶│  Transformation │───▶│         mBOM            │  │
│  │  Database   │    │     Engine      │    │       Database          │  │
│  │  (SQLite)   │    │  (Rule-based)   │    │       (SQLite)          │  │
│  └─────────────┘    └─────────────────┘    └─────────────────────────┘  │
│         │                    │                        │                │
│         │                    ▼                        │                │
│         │           ┌─────────────────┐               │                │
│         │           │  Rule Registry  │               │                │
│         │           │  (Priority Queue) │               │                │
│         │           └─────────────────┘               │                │
│         │                    │                        │                │
│         ▼                    ▼                        ▼                │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                      Audit Trail                                │    │
│  │  Every decision logged: which rule, which part, why, when       │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    Validation Layer                              │    │
│  │  UOM check | Build sequence check | Orphan check | Unmapped flag │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   FastAPI REST    │
                    │   API Gateway     │
                    └─────────────────┘
```

### Data Flow

```
1. Load eBOM parts from SQLite
2. Load active transformation rules (priority-sorted)
3. For each eBOM part:
   a. Match against rules in priority order
   b. Apply first matching rule
   c. Generate mBOM line(s)
   d. Write audit entry
4. Run validation layer on generated mBOM
5. Flag unmapped parts for human review
6. Return summary + validation report
```

---

## Project Structure

```
ebom-mbom-platform/
├── models.py                 # Data models (EBOMPart, MBOMPart, Rule, Audit, Validation)
├── database.py               # SQLite schema, CRUD, recursive CTEs, indexes
├── transformation_engine.py  # Core rule engine (5 rule types)
├── sample_data.py            # Synthetic electromechanical BOM + 5 rules
├── api.py                    # FastAPI REST endpoints
├── test_suite.py             # 40+ unit tests across 7 test classes
├── main.py                   # CLI interface (init, transform, report, audit, export)
├── requirements.txt          # Python dependencies
└── README.md                 # This file (interview script)
```

---

## Core Features

### 1. Five Transformation Rule Types

| Rule | Purpose | Example |
|------|---------|---------|
| **EXCLUDE** | Drop design-only parts | Virtual reference envelope |
| **SPLIT** | Explode assembly into components | Harness → wire + connector + heat-shrink |
| **MERGE** | Consolidate into procurement kit | 4 fasteners → 1 fastener kit |
| **ADD** | Inject manufacturing consumables | Thermal paste, packaging, labels |
| **REQUANTIFY** | Adjust for scrap/batch sizing | Wire: 1.0m → 1.08m (8% scrap) |

### 2. Full Audit Trail

Every transformation decision is logged with:
- Source eBOM part snapshot (before state)
- Generated mBOM line(s) (after state)
- Rule ID, name, type
- Justification and reason code
- Timestamp and processing engine version

### 3. Validation Layer

Post-transformation checks:
- ✅ Valid UOM and positive quantity on every line
- ✅ Every part maps to a build sequence
- ✅ No orphaned parent references
- ⚠️ Unmapped parts flagged for human review (never silently dropped)

### 4. Configurable Rule Engine

Rules are stored in the database and evaluated by priority. New rules can be added via API without code changes.

### 5. Recursive BOM Tree Queries

SQLite CTEs for traversing multi-level BOM hierarchies.

---

## Transformation Rules

### Rule 1: EXCLUDE Virtual Parts

```
Pattern:     part_type = VIRTUAL
Action:      Drop from mBOM
Reason:      "Virtual parts are CAD-only constructs with no physical counterpart"
Code:        VIRTUAL_NO_PHYSICAL
```

**Example**: `REF-ENV-001` (Motor Envelope Reference) exists in CAD to ensure clearance but is never manufactured or purchased.

### Rule 2: SPLIT Wire Harness

```
Pattern:     HARNESS-ASM-001
Action:      Split into 4 procurement items:
              - WIRE-18AWG-RED-001 (2x)
              - WIRE-18AWG-BLK-001 (2x)
              - CONN-CRIMP-001 (4x)
              - HS-6MM-001 (2x)
Reason:      "Manufacturing procures individual items separately"
Code:        HARNESS_DECOMPOSITION
```

### Rule 3: MERGE Fasteners into Kit

```
Pattern:     ^(SCREW-M3|WASHER-M3|NUT-M3).*
Action:      Merge into KIT-FASTENER-M3-001
              Total qty = sum of all individual quantities
Reason:      "Reduce line-side inventory and picking errors"
Code:        FASTENER_KIT_CONSOLIDATION
```

### Rule 4: ADD Manufacturing Consumables

```
Trigger:    MOTOR-DC-001 present in assembly
Action:     Inject:
            - THERMAL-PASTE-001 (1x)
            - PKG-FOAM-001 (1x)
            - LABEL-SERIAL-001 (1x)
Reason:     "Required for production but never modeled in CAD"
Code:       MFG_CONSUMABLES
```

### Rule 5: REQUANTIFY for Scrap Rate

```
Pattern:     WIRE-18AWG.*
Action:      Multiply quantity by 1.08 (8% scrap)
Reason:      "Wire cutting produces scrap from end trimming and mis-crimps"
Code:        SCRAP_8PCT_WIRE
```

---

## Running the Project

### Prerequisites

```bash
pip install fastapi uvicorn pydantic
```

### Quick Start

```bash
# 1. Initialize database with sample data
python main.py init

# 2. Run transformation pipeline
python main.py transform

# 3. View report
python main.py report

# 4. View audit trail
python main.py audit

# 5. Run validation
python main.py validate

# 6. Run complete demo
python main.py demo
```

### API Server

```bash
python api.py
# Server runs on http://localhost:8000
# Docs at http://localhost:8000/docs
```

### Key Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/transform` | Execute transformation pipeline |
| GET | `/api/v1/ebom` | List eBOM parts |
| GET | `/api/v1/mbom` | List mBOM lines |
| GET | `/api/v1/audit` | Full audit trail |
| GET | `/api/v1/validation` | Validation results |
| GET | `/api/v1/summary` | Transformation summary |
| GET | `/api/v1/unmapped` | Parts needing human review |

---

## Testing

```bash
# Run full test suite
python main.py test

# Or directly
python test_suite.py
```

### Test Coverage (7 classes, 40+ tests)

| Test Class | Coverage |
|------------|----------|
| `TestDataModels` | Model creation and serialization |
| `TestDatabaseOperations` | CRUD, recursive CTEs, indexes |
| `TestTransformationRules` | All 5 rule types individually |
| `TestValidationLayer` | UOM, build sequence, orphan checks |
| `TestUnmappedParts` | Flagging behavior (not silently dropped) |
| `TestEndToEndPipeline` | Full pipeline integration |
| `TestEdgeCases` | Empty BOM, no rules, boundary conditions |

---

## Interview Talking Points

### 1. The eBOM vs mBOM Conceptual Difference

> "The eBOM is the designer's view — organized by function, tied to CAD, includes virtual parts. The mBOM is the factory's view — organized by build sequence, includes consumables, reflects how things are actually built. The conversion between them is non-trivial because it's not a 1:1 mapping."

### 2. One Hard Decision in the Rule Engine

> "I decided to make the rule engine **priority-ordered with first-match wins** rather than allowing multiple rules to fire on the same part. This was a deliberate trade-off: it prevents conflicting rule interactions but means additive rules like ADD must be designed as side-effects of other matches. In a real system, I'd implement a rule conflict resolution layer with explicit precedence and dependency graphs."

### 3. Why Unmapped Parts Are Flagged, Not Dropped

> "This is the most important design decision. In production PLM, silently dropping a part is catastrophic — it means a missing component on the assembly line. I implemented an explicit `unmapped_parts` table that queues items for human review. This mirrors how real PDM systems handle exceptions."

### 4. The Audit Trail

> "Traceability is non-negotiable in manufacturing. Every mBOM line must answer: 'Where did this come from?' My audit log captures the before-state (eBOM snapshot), the rule that fired, the after-state (mBOM lines), the justification, and the timestamp. This is what auditors and manufacturing engineers need."

### 5. Validation Layer Design

> "I separated validation from transformation. The engine produces the mBOM, then an independent validation layer checks business rules. This separation of concerns means validation rules can be added or modified without touching the transformation logic — critical for enterprise systems where validation requirements change frequently."

---

## What I'd Do Differently at Enterprise Scale

### 1. Concurrent Revision Handling

> "This toy version assumes a single revision. At scale, I'd implement:
> - **Revision branching**: eBOM rev B might map to mBOM rev A+1
> - **Change impact analysis**: When an eBOM part changes, which mBOM lines are affected?
> - **Effective dating**: Rules effective from date X to date Y"

### 2. Performance at 100,000+ Part BOMs

> "SQLite with Python is fine for demos. At enterprise scale:
> - **PostgreSQL** with proper indexing and partitioning
> - **Graph database** (Neo4j) for BOM hierarchy queries
> - **Streaming processing**: Process BOMs in chunks, not all-at-once
> - **Caching**: Rule matching results cached by part pattern hash"

### 3. CAD/PDM Integration

> "Real integration would:
> - **Read eBOM directly** from Siemens Teamcenter, PTC Windchill, or Dassault ENOVIA via their APIs
> - **Sync CAD metadata**: material specs, tolerances, surface finishes
> - **Bi-directional sync**: mBOM changes feedback to eBOM when design changes are required"

### 4. Rule Engine Sophistication

> "Current rules are pattern-based. At scale I'd add:
> - **Expression language**: Rules as configurable expressions, not hardcoded logic
> - **Machine learning**: Auto-suggest rules based on historical transformations
> - **Simulation**: Preview mBOM before committing changes"

### 5. Multi-Site Manufacturing

> "Different factories may need different mBOMs from the same eBOM:
> - **Site-specific rules**: Factory A kits fasteners, Factory B doesn't
> - **Supplier variation**: Same part, different suppliers per region
> - **Regulatory compliance**: Different consumables for different markets"

---

## Sample Dataset

The synthetic dataset models a **motor mount assembly** — an electromechanical sub-assembly rich enough to need all five rule types:

```
ASM-MOTOR-MOUNT-001 (top-level)
├── SUB-PCB-001 (PCB sub-assembly)
│   ├── PCB-001 (main board)
│   ├── RES-10K (resistor ×4)
│   └── CAP-100U (capacitor ×2)
├── SUB-HARNESS-001 (wiring harness)
│   ├── HARNESS-ASM-001 → SPLIT into wire + connector + heat-shrink
│   └── CONN-PWR-001 (power connector)
├── MOTOR-DC-001 → REQUANTIFY (batch sizing)
├── BRACKET-AL-001 (aluminum bracket)
├── SCREW-M3x12-001 → MERGE into fastener kit
├── SCREW-M3x16-001 → MERGE into fastener kit
├── WASHER-M3-001 → MERGE into fastener kit
├── NUT-M3-001 → MERGE into fastener kit
├── REF-ENV-001 → EXCLUDE (virtual)
└── PAD-ISO-001 (isolation pad)

ADDed for manufacturing (triggered by MOTOR-DC-001):
├── THERMAL-PASTE-001
├── PKG-FOAM-001
└── LABEL-SERIAL-001
```

---

## License

MIT License — Built for demonstration and interview purposes.

---

## Author

Built as a portfolio project demonstrating enterprise systems engineering, PLM/PDM domain knowledge, and production-grade Python development.
