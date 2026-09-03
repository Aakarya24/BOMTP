"""
================================================================================
Sample Dataset — Electromechanical Motor Mount Assembly
================================================================================

A realistic synthetic dataset for demonstrating all five transformation rule types:
  - EXCLUDE: Virtual reference envelope
  - SPLIT: Wire harness assembly → wire + connector + heat-shrink
  - MERGE: Individual fasteners → fastener kit
  - ADD: Adhesive, packaging (no eBOM counterpart)
  - REQUANTIFY: Wire with scrap rate, motor with batch sizing

Assembly hierarchy:
  ASM-MOTOR-MOUNT-001 (top-level)
    ├── SUB-PCB-001 (printed circuit board sub-assembly)
    │   ├── PCB-001 (main board)
    │   ├── RES-10K (resistor)
    │   └── CAP-100U (capacitor)
    ├── SUB-HARNESS-001 (wiring harness sub-assembly)
    │   ├── HARNESS-ASM-001 (wire harness assembly) → SPLIT
    │   └── CONN-PWR-001 (power connector)
    ├── MOTOR-DC-001 (DC motor) → REQUANTIFY
    ├── BRACKET-AL-001 (aluminum bracket)
    ├── SCREW-M3x12-001 (fastener) → MERGE
    ├── SCREW-M3x16-001 (fastener) → MERGE
    ├── WASHER-M3-001 (fastener) → MERGE
    ├── NUT-M3-001 (fastener) → MERGE
    ├── REF-ENV-001 (reference envelope) → EXCLUDE
    └── PAD-ISO-001 (isolation pad)
"""

from datetime import datetime
from models import EBOMPart, PartType, TransformationRule, RuleType, WorkCenter
from database import Database


def seed_work_centers(db: Database) -> None:
    """Seed manufacturing work centers."""
    centers = [
        WorkCenter("WC-SMT", "SMT Line", 10, "Surface mount technology assembly", 
                   ["component_placement", "soldering", "inspection"]),
        WorkCenter("WC-HARNESS", "Wire Harness Station", 20, 
                   "Wire cutting, stripping, crimping, and harness assembly",
                   ["wire_cutting", "crimping", "heat_shrink", "testing"]),
        WorkCenter("WC-MECH-ASM", "Mechanical Assembly", 30,
                   "Mechanical component assembly and fastening",
                   ["fastening", "torqueing", "alignment", "inspection"]),
        WorkCenter("WC-FINAL-ASM", "Final Assembly", 40,
                   "Final product assembly and testing",
                   ["integration", "testing", "calibration", "packaging"]),
        WorkCenter("WC-KITTING", "Parts Kitting", 15,
                   "Pre-assembly parts preparation and kitting",
                   ["kitting", "labeling", "staging"]),
        WorkCenter("WC-QC", "Quality Control", 50,
                   "Incoming inspection and final quality check",
                   ["inspection", "testing", "documentation"]),
    ]
    for wc in centers:
        db.insert_work_center(wc)


def seed_ebom_parts(db: Database) -> None:
    """Seed the engineering BOM with realistic industrial parts."""
    parts = [
        # === TOP-LEVEL ASSEMBLY ===
        EBOMPart(
            part_id="ASM-MOTOR-MOUNT-001",
            part_name="Motor Mount Assembly",
            parent_assembly_id=None,
            quantity_per_parent=1.0,
            part_type=PartType.MANUFACTURED,
            revision="A",
            unit_of_measure="EA",
            cad_reference_id="CAD-ASM-001",
            material_spec=None,
            drawing_number="DWG-ASM-001-REV-A"
        ),

        # === PCB SUB-ASSEMBLY ===
        EBOMPart(
            part_id="SUB-PCB-001",
            part_name="PCB Sub-Assembly",
            parent_assembly_id="ASM-MOTOR-MOUNT-001",
            quantity_per_parent=1.0,
            part_type=PartType.MANUFACTURED,
            revision="A",
            unit_of_measure="EA",
            cad_reference_id="CAD-SUB-001",
            material_spec=None,
            drawing_number="DWG-SUB-001-REV-A"
        ),
        EBOMPart(
            part_id="PCB-001",
            part_name="Main Control PCB",
            parent_assembly_id="SUB-PCB-001",
            quantity_per_parent=1.0,
            part_type=PartType.PURCHASED,
            revision="B",
            unit_of_measure="EA",
            cad_reference_id="CAD-PCB-001",
            material_spec="FR4-TG170",
            drawing_number="DWG-PCB-001-REV-B"
        ),
        EBOMPart(
            part_id="RES-10K",
            part_name="Resistor 10K Ohm 1%",
            parent_assembly_id="SUB-PCB-001",
            quantity_per_parent=4.0,
            part_type=PartType.STANDARD,
            revision="A",
            unit_of_measure="EA",
            cad_reference_id=None,
            material_spec=None,
            drawing_number=None
        ),
        EBOMPart(
            part_id="CAP-100U",
            part_name="Capacitor 100uF 25V",
            parent_assembly_id="SUB-PCB-001",
            quantity_per_parent=2.0,
            part_type=PartType.STANDARD,
            revision="A",
            unit_of_measure="EA",
            cad_reference_id=None,
            material_spec=None,
            drawing_number=None
        ),

        # === WIRING HARNESS SUB-ASSEMBLY ===
        EBOMPart(
            part_id="SUB-HARNESS-001",
            part_name="Wiring Harness Sub-Assembly",
            parent_assembly_id="ASM-MOTOR-MOUNT-001",
            quantity_per_parent=1.0,
            part_type=PartType.MANUFACTURED,
            revision="A",
            unit_of_measure="EA",
            cad_reference_id="CAD-SUB-002",
            material_spec=None,
            drawing_number="DWG-SUB-002-REV-A"
        ),
        # This part will be SPLIT into wire + connector + heat-shrink
        EBOMPart(
            part_id="HARNESS-ASM-001",
            part_name="Wire Harness Assembly",
            parent_assembly_id="SUB-HARNESS-001",
            quantity_per_parent=1.0,
            part_type=PartType.MANUFACTURED,
            revision="C",
            unit_of_measure="EA",
            cad_reference_id="CAD-HARNESS-001",
            material_spec="PVC-Insulated-Copper",
            drawing_number="DWG-HARNESS-001-REV-C"
        ),
        EBOMPart(
            part_id="CONN-PWR-001",
            part_name="Power Connector 2P",
            parent_assembly_id="SUB-HARNESS-001",
            quantity_per_parent=1.0,
            part_type=PartType.PURCHASED,
            revision="A",
            unit_of_measure="EA",
            cad_reference_id="CAD-CONN-001",
            material_spec="PA66-GF30",
            drawing_number="DWG-CONN-001-REV-A"
        ),

        # === MECHANICAL COMPONENTS ===
        EBOMPart(
            part_id="MOTOR-DC-001",
            part_name="DC Motor 12V 50W",
            parent_assembly_id="ASM-MOTOR-MOUNT-001",
            quantity_per_parent=1.0,
            part_type=PartType.PURCHASED,
            revision="B",
            unit_of_measure="EA",
            cad_reference_id="CAD-MOTOR-001",
            material_spec=None,
            drawing_number="DWG-MOTOR-001-REV-B"
        ),
        EBOMPart(
            part_id="BRACKET-AL-001",
            part_name="Aluminum Mounting Bracket",
            parent_assembly_id="ASM-MOTOR-MOUNT-001",
            quantity_per_parent=1.0,
            part_type=PartType.MANUFACTURED,
            revision="A",
            unit_of_measure="EA",
            cad_reference_id="CAD-BRACKET-001",
            material_spec="AL6061-T6",
            drawing_number="DWG-BRACKET-001-REV-A"
        ),

        # === FASTENERS (will be MERGED into a kit) ===
        EBOMPart(
            part_id="SCREW-M3x12-001",
            part_name="Machine Screw M3x12 SS",
            parent_assembly_id="ASM-MOTOR-MOUNT-001",
            quantity_per_parent=4.0,
            part_type=PartType.FASTENER,
            revision="A",
            unit_of_measure="EA",
            cad_reference_id=None,
            material_spec="A2-70",
            drawing_number=None
        ),
        EBOMPart(
            part_id="SCREW-M3x16-001",
            part_name="Machine Screw M3x16 SS",
            parent_assembly_id="ASM-MOTOR-MOUNT-001",
            quantity_per_parent=2.0,
            part_type=PartType.FASTENER,
            revision="A",
            unit_of_measure="EA",
            cad_reference_id=None,
            material_spec="A2-70",
            drawing_number=None
        ),
        EBOMPart(
            part_id="WASHER-M3-001",
            part_name="Flat Washer M3 SS",
            parent_assembly_id="ASM-MOTOR-MOUNT-001",
            quantity_per_parent=6.0,
            part_type=PartType.FASTENER,
            revision="A",
            unit_of_measure="EA",
            cad_reference_id=None,
            material_spec="A2-70",
            drawing_number=None
        ),
        EBOMPart(
            part_id="NUT-M3-001",
            part_name="Hex Nut M3 SS",
            parent_assembly_id="ASM-MOTOR-MOUNT-001",
            quantity_per_parent=6.0,
            part_type=PartType.FASTENER,
            revision="A",
            unit_of_measure="EA",
            cad_reference_id=None,
            material_spec="A2-70",
            drawing_number=None
        ),

        # === VIRTUAL PART (will be EXCLUDED) ===
        EBOMPart(
            part_id="REF-ENV-001",
            part_name="Motor Envelope Reference",
            parent_assembly_id="ASM-MOTOR-MOUNT-001",
            quantity_per_parent=1.0,
            part_type=PartType.VIRTUAL,
            revision="A",
            unit_of_measure="EA",
            cad_reference_id="CAD-REF-001",
            material_spec=None,
            drawing_number=None
        ),

        # === ISOLATION PAD ===
        EBOMPart(
            part_id="PAD-ISO-001",
            part_name="Vibration Isolation Pad",
            parent_assembly_id="ASM-MOTOR-MOUNT-001",
            quantity_per_parent=4.0,
            part_type=PartType.PURCHASED,
            revision="A",
            unit_of_measure="EA",
            cad_reference_id="CAD-PAD-001",
            material_spec="NBR-70",
            drawing_number="DWG-PAD-001-REV-A"
        ),
    ]

    for part in parts:
        db.insert_ebom_part(part)


def seed_transformation_rules(db: Database) -> None:
    """Seed the five core transformation rules."""
    rules = [
        # === RULE 1: EXCLUDE — Drop virtual/reference parts ===
        TransformationRule(
            rule_id="RULE-EXCLUDE-001",
            rule_type=RuleType.EXCLUDE,
            rule_name="Exclude Virtual and Reference Parts",
            description="Drop parts that exist only for design intent (no physical manufacturing step)",
            source_part_pattern=".*",
            source_part_type_filter=PartType.VIRTUAL,
            target_mappings=[],
            justification="Virtual parts are CAD-only constructs with no physical counterpart. Including them in mBOM would cause procurement errors.",
            reason_code="VIRTUAL_NO_PHYSICAL",
            priority=10,
            is_active=True
        ),

        # === RULE 2: SPLIT — Wire harness → components ===
        TransformationRule(
            rule_id="RULE-SPLIT-001",
            rule_type=RuleType.SPLIT,
            rule_name="Split Wire Harness Assembly",
            description="Explode wire harness assembly into individual procurement items",
            source_part_pattern="HARNESS-ASM-001",
            target_mappings=[
                {
                    "target_part_id": "WIRE-18AWG-RED-001",
                    "target_name": "18AWG Red Wire 500mm",
                    "quantity_ratio": 2.0,
                    "unit_of_measure": "EA",
                    "work_center": "WC-HARNESS",
                    "lead_time_days": 5,
                    "supplier_id": "SUP-WIRE-001"
                },
                {
                    "target_part_id": "WIRE-18AWG-BLK-001",
                    "target_name": "18AWG Black Wire 500mm",
                    "quantity_ratio": 2.0,
                    "unit_of_measure": "EA",
                    "work_center": "WC-HARNESS",
                    "lead_time_days": 5,
                    "supplier_id": "SUP-WIRE-001"
                },
                {
                    "target_part_id": "CONN-CRIMP-001",
                    "target_name": "Crimp Terminal 2.8mm",
                    "quantity_ratio": 4.0,
                    "unit_of_measure": "EA",
                    "work_center": "WC-HARNESS",
                    "lead_time_days": 3,
                    "supplier_id": "SUP-CONN-001"
                },
                {
                    "target_part_id": "HS-6MM-001",
                    "target_name": "Heat Shrink Tube 6mm",
                    "quantity_ratio": 2.0,
                    "unit_of_measure": "EA",
                    "work_center": "WC-HARNESS",
                    "lead_time_days": 2,
                    "supplier_id": "SUP-HS-001"
                }
            ],
            justification="Wire harness is an assembly-level design item. Manufacturing procures individual wire, connector, and heat-shrink items separately.",
            reason_code="HARNESS_DECOMPOSITION",
            priority=20,
            is_active=True
        ),

        # === RULE 3: MERGE — Fasteners into kit ===
        TransformationRule(
            rule_id="RULE-MERGE-001",
            rule_type=RuleType.MERGE,
            rule_name="Merge M3 Fasteners into Kit",
            description="Consolidate individual M3 fasteners into a single procurement kit",
            source_part_pattern="^(SCREW-M3|WASHER-M3|NUT-M3).*",
            target_mappings=[
                {
                    "target_part_id": "KIT-FASTENER-M3-001",
                    "target_name": "M3 Fastener Kit (Screws + Washers + Nuts)",
                    "unit_of_measure": "KIT",
                    "work_center": "WC-KITTING",
                    "lead_time_days": 7,
                    "supplier_id": "SUP-FASTENER-001"
                }
            ],
            justification="Individual fasteners are design-level detail. Procurement issues fasteners as pre-kitted sets to reduce line-side inventory and picking errors.",
            reason_code="FASTENER_KIT_CONSOLIDATION",
            priority=30,
            is_active=True
        ),

        # === RULE 4: ADD — Manufacturing-only items ===
        # Triggered by presence of motor — add thermal paste and packaging
        TransformationRule(
            rule_id="RULE-ADD-001",
            rule_type=RuleType.ADD,
            rule_name="Add Motor Assembly Consumables",
            description="Inject manufacturing-only items when motor is present in assembly",
            source_part_pattern="MOTOR-DC-001",
            target_mappings=[
                {
                    "target_part_id": "THERMAL-PASTE-001",
                    "target_name": "Thermal Conductive Paste 2g",
                    "quantity": 1.0,
                    "unit_of_measure": "EA",
                    "work_center": "WC-MECH-ASM",
                    "lead_time_days": 1,
                    "supplier_id": "SUP-CHEM-001"
                },
                {
                    "target_part_id": "PKG-FOAM-001",
                    "target_name": "Protective Foam Insert",
                    "quantity": 1.0,
                    "unit_of_measure": "EA",
                    "work_center": "WC-FINAL-ASM",
                    "lead_time_days": 2,
                    "supplier_id": "SUP-PKG-001"
                },
                {
                    "target_part_id": "LABEL-SERIAL-001",
                    "target_name": "Serial Number Label",
                    "quantity": 1.0,
                    "unit_of_measure": "EA",
                    "work_center": "WC-FINAL-ASM",
                    "lead_time_days": 1,
                    "supplier_id": "SUP-LABEL-001"
                }
            ],
            justification="Thermal paste, packaging, and labels are required for production but never modeled in CAD. They must be injected during eBOM→mBOM transformation.",
            reason_code="MFG_CONSUMABLES",
            priority=40,
            is_active=True
        ),

        # === RULE 5: REQUANTIFY — Adjust for scrap rate ===
        TransformationRule(
            rule_id="RULE-REQUANTIFY-001",
            rule_type=RuleType.REQUANTIFY,
            rule_name="Apply Wire Scrap Rate",
            description="Increase wire quantities to account for cutting and stripping scrap",
            source_part_pattern="WIRE-18AWG.*",
            target_mappings=[
                {
                    "multiplier": 1.08,
                    "reason": "scrap_rate",
                    "work_center": "WC-HARNESS",
                    "lead_time_days": 5
                }
            ],
            justification="Wire cutting and stripping operations produce approximately 8% scrap due to end trimming, mis-crimps, and quality rejects. mBOM must reflect actual consumption.",
            reason_code="SCRAP_8PCT_WIRE",
            priority=50,
            is_active=True
        ),

        # Additional requantify for motor (batch sizing)
        TransformationRule(
            rule_id="RULE-REQUANTIFY-002",
            rule_type=RuleType.REQUANTIFY,
            rule_name="Motor Batch Sizing Adjustment",
            description="Round motor quantity to supplier minimum order quantity",
            source_part_pattern="MOTOR-DC-001",
            target_mappings=[
                {
                    "multiplier": 1.0,
                    "reason": "batch_sizing",
                    "work_center": "WC-MECH-ASM",
                    "lead_time_days": 14
                }
            ],
            justification="Motor supplier requires minimum order quantity of 1 unit. No quantity adjustment needed for single-unit assembly, but rule ensures batch logic is documented.",
            reason_code="BATCH_MOQ_1",
            priority=55,
            is_active=True
        ),
    ]

    for rule in rules:
        db.insert_rule(rule)


def initialize_database(db_path: str = "ebom_mbom.db") -> Database:
    """Initialize the full database with sample data."""
    import os
    if os.path.exists(db_path):
        os.remove(db_path)

    db = Database(db_path)
    seed_work_centers(db)
    seed_ebom_parts(db)
    seed_transformation_rules(db)
    return db


if __name__ == "__main__":
    db = initialize_database()
    print("Database initialized with sample data.")
    print(f"Work centers: {len(db.get_work_centers())}")
    print(f"eBOM parts: {len(db.get_all_ebom_parts())}")
    print(f"Transformation rules: {len(db.get_all_rules())}")
