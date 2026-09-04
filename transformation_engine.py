"""
================================================================================
Transformation Engine — eBOM → mBOM Rule Processor
================================================================================

Implements the five core transformation rule types:
  1. EXCLUDE   — Drop virtual/reference parts
  2. SPLIT     — One eBOM → multiple mBOM items
  3. MERGE     — Multiple eBOM → one mBOM item
  4. ADD       — Inject manufacturing-only items
  5. REQUANTIFY — Adjust quantities for production reality

Design decisions:
  - Rules are evaluated in priority order (lower priority = first)
  - Each eBOM part is matched against ALL active rules
  - First matching rule wins (configurable)
  - Unmatched parts are FLAGGED, not silently dropped
  - Full audit trail for every decision
"""

import re
import uuid
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from models import *
from database import Database


class TransformationEngine:
    """
    Core transformation engine that processes eBOM parts through
    configurable rules to produce an mBOM with full traceability.
    """

    def __init__(self, db: Database):
        self.db = db
        self._rule_cache: List[Dict[str, Any]] = []
        self._work_centers: Dict[str, Dict[str, Any]] = {}
        self._build_sequence_counter = 0
        self._audit_entries: List[AuditEntry] = []
        self._unmapped_parts: List[Dict[str, Any]] = []

    def _next_build_sequence(self) -> int:
        self._build_sequence_counter += 10
        return self._build_sequence_counter

    def _generate_id(self, prefix: str = "") -> str:
        return f"{prefix}{uuid.uuid4().hex[:12].upper()}"

    def _match_rule(self, rule: Dict[str, Any], part: Dict[str, Any]) -> bool:
        """Check if a rule matches an eBOM part."""
        # Pattern match on part_id or part_name
        pattern = rule.get('source_part_pattern', '')
        if pattern:
            if not (re.search(pattern, part.get('part_id', '')) or 
                    re.search(pattern, part.get('part_name', ''))):
                return False

        # Part type filter
        type_filter = rule.get('source_part_type_filter')
        if type_filter and part.get('part_type') != type_filter:
            return False

        # Parent assembly filter
        parent_filter = rule.get('parent_assembly_filter')
        if parent_filter and part.get('parent_assembly_id') != parent_filter:
            return False

        return True

    def _create_mbom_line(self, part_id: str, part_name: str, 
                          parent_assembly_id: Optional[str],
                          quantity: float, uom: str,
                          work_center: str, source_type: MBOMSourceType,
                          source_ebom_ids: List[str], rule_applied: str,
                          lead_time: Optional[int] = None,
                          supplier: Optional[str] = None) -> MBOMPart:
        """Factory for creating mBOM line items."""
        return MBOMPart(
            mbom_line_id=self._generate_id("MB"),
            part_id=part_id,
            part_name=part_name,
            parent_assembly_id=parent_assembly_id,
            quantity_per_unit=quantity,
            unit_of_measure=uom,
            build_sequence=self._next_build_sequence(),
            work_center=work_center,
            source_type=source_type,
            source_ebom_part_ids=source_ebom_ids,
            rule_applied=rule_applied,
            lead_time_days=lead_time,
            supplier_id=supplier
        )

    def _log_audit(self, ebom_part: Dict[str, Any], rule: Dict[str, Any],
                   mbom_created: List[MBOMPart], mbom_modified: List[MBOMPart] = None) -> None:
        """Create a complete audit trail entry."""
        entry = AuditEntry(
            audit_id=self._generate_id("AUD"),
            ebom_part_id=ebom_part['part_id'],
            rule_id=rule['rule_id'],
            rule_type=RuleType(rule['rule_type']),
            rule_name=rule['rule_name'],
            ebom_state=ebom_part,
            mbom_lines_created=[m.to_dict() for m in mbom_created] if mbom_created else [],
            mbom_lines_modified=[m.to_dict() for m in mbom_modified] if mbom_modified else [],
            justification=rule['justification'],
            reason_code=rule['reason_code']
        )
        self._audit_entries.append(entry)
        self.db.insert_audit_entry(entry)

    def _apply_exclude(self, rule: Dict[str, Any], part: Dict[str, Any]) -> List[MBOMPart]:
        """
        EXCLUDE rule: Drop virtual/reference parts from mBOM.

        Rationale: Virtual parts (reference envelopes, design-intent geometry)
        exist only in CAD and have no physical manufacturing step.
        """
        self._log_audit(part, rule, [], [])
        return []  # No mBOM lines created

    def _apply_split(self, rule: Dict[str, Any], part: Dict[str, Any]) -> List[MBOMPart]:
        """
        SPLIT rule: One eBOM part explodes into multiple mBOM line items.

        Example: "Wire Harness Assembly" (eBOM) → Wire + Connector + Heat-shrink (mBOM)
        Each sub-item gets its own part number, quantity ratio, and work center.
        """
        mappings = json.loads(rule.get('target_mappings', '[]'))
        mbom_lines = []

        for mapping in mappings:
            qty = part['quantity_per_parent'] * mapping.get('quantity_ratio', 1.0)
            line = self._create_mbom_line(
                part_id=mapping['target_part_id'],
                part_name=mapping['target_name'],
                parent_assembly_id=part.get('parent_assembly_id'),
                quantity=round(qty, 4),
                uom=mapping.get('unit_of_measure', part['unit_of_measure']),
                work_center=mapping.get('work_center', 'WC-ASSEMBLY'),
                source_type=MBOMSourceType.SPLIT_FROM_EBOM,
                source_ebom_ids=[part['part_id']],
                rule_applied=rule['rule_id'],
                lead_time=mapping.get('lead_time_days'),
                supplier=mapping.get('supplier_id')
            )
            mbom_lines.append(line)
            self.db.insert_mbom_part(line)

        self._log_audit(part, rule, mbom_lines)
        return mbom_lines

    def _apply_merge(self, rule: Dict[str, Any], part: Dict[str, Any],
                     all_parts: List[Dict[str, Any]], 
                     already_merged: set) -> List[MBOMPart]:
        """
        MERGE rule: Multiple eBOM parts collapse into a single mBOM procurement item.

        Example: M3x12 screw, M3x16 screw, M3 washer → "M3 Fastener Kit"
        This is tricky because we need to collect ALL matching parts before creating
        the merged line. We handle this by tracking already-merged parts.

        NOTE: This simplified version creates one merged line per matched part.
        In production, you'd batch-process all parts first, then create merged lines.
        """
        if part['part_id'] in already_merged:
            return []

        # Find all parts that match this merge rule
        pattern = rule.get('source_part_pattern', '')
        matching_parts = [p for p in all_parts 
                         if re.search(pattern, p['part_id']) and p['part_id'] not in already_merged]

        if len(matching_parts) < 2:
            # Not enough parts to merge — fall through to default handling
            return []

        # Mark all as merged
        for p in matching_parts:
            already_merged.add(p['part_id'])

        mappings = json.loads(rule.get('target_mappings', '[]'))
        if not mappings:
            return []

        target = mappings[0]
        total_qty = sum(p['quantity_per_parent'] for p in matching_parts)

        line = self._create_mbom_line(
            part_id=target['target_part_id'],
            part_name=target['target_name'],
            parent_assembly_id=matching_parts[0].get('parent_assembly_id'),
            quantity=round(total_qty, 4),
            uom=target.get('unit_of_measure', matching_parts[0]['unit_of_measure']),
            work_center=target.get('work_center', 'WC-KITTING'),
            source_type=MBOMSourceType.MERGED_EBOM,
            source_ebom_ids=[p['part_id'] for p in matching_parts],
            rule_applied=rule['rule_id'],
            lead_time=target.get('lead_time_days'),
            supplier=target.get('supplier_id')
        )
        self.db.insert_mbom_part(line)

        # Audit for each source part
        for p in matching_parts:
            self._log_audit(p, rule, [line])

        return [line]

    def _apply_add(self, rule: Dict[str, Any], part: Dict[str, Any]) -> List[MBOMPart]:
        """
        ADD rule: Inject manufacturing-only items with no eBOM counterpart.

        Example: Adhesive, packaging foam, calibration fluid, shop-floor consumables.
        These items never appear in CAD models but are essential for production.

        ADD rules are triggered by context (e.g., "when part X is present, add Y").
        """
        mappings = json.loads(rule.get('target_mappings', '[]'))
        mbom_lines = []

        for mapping in mappings:
            line = self._create_mbom_line(
                part_id=mapping['target_part_id'],
                part_name=mapping['target_name'],
                parent_assembly_id=part.get('parent_assembly_id'),
                quantity=mapping.get('quantity', 1.0),
                uom=mapping.get('unit_of_measure', 'EA'),
                work_center=mapping.get('work_center', 'WC-ASSEMBLY'),
                source_type=MBOMSourceType.ADDED_FOR_MANUFACTURING,
                source_ebom_ids=[part['part_id']],  # Triggered by this eBOM part
                rule_applied=rule['rule_id'],
                lead_time=mapping.get('lead_time_days'),
                supplier=mapping.get('supplier_id')
            )
            mbom_lines.append(line)
            self.db.insert_mbom_part(line)

        self._log_audit(part, rule, mbom_lines)
        return mbom_lines

    def _apply_requantify(self, rule: Dict[str, Any], part: Dict[str, Any]) -> List[MBOMPart]:
        """
        REQUANTIFY rule: Recompute quantity-per-unit for production reality.

        Example: eBOM says 1.0 wire per assembly, but production needs 1.05
        to account for 5% scrap rate during cutting/stripping.

        Another: Batch sizing — eBOM quantity is per-assembly, but supplier
        ships in lots of 100, so mBOM rounds up.
        """
        mappings = json.loads(rule.get('target_mappings', '[]'))
        if not mappings:
            return []

        params = mappings[0]
        multiplier = params.get('multiplier', 1.0)
        new_qty = round(part['quantity_per_parent'] * multiplier, 4)

        line = self._create_mbom_line(
            part_id=part['part_id'],
            part_name=part['part_name'],
            parent_assembly_id=part.get('parent_assembly_id'),
            quantity=new_qty,
            uom=part['unit_of_measure'],
            work_center=params.get('work_center', 'WC-ASSEMBLY'),
            source_type=MBOMSourceType.REQUANTIFIED,
            source_ebom_ids=[part['part_id']],
            rule_applied=rule['rule_id'],
            lead_time=params.get('lead_time_days'),
            supplier=params.get('supplier_id')
        )
        self.db.insert_mbom_part(line)

        self._log_audit(part, rule, [line])
        return [line]

    def _apply_default_pass_through(self, part: Dict[str, Any]) -> List[MBOMPart]:
        """
        Default behavior: Pass eBOM part through to mBOM unchanged.
        Used when no specific rule matches a manufacturable/purchased part.
        """
        line = self._create_mbom_line(
            part_id=part['part_id'],
            part_name=part['part_name'],
            parent_assembly_id=part.get('parent_assembly_id'),
            quantity=part['quantity_per_parent'],
            uom=part['unit_of_measure'],
            work_center='WC-ASSEMBLY',  # Default work center
            source_type=MBOMSourceType.FROM_EBOM,
            source_ebom_ids=[part['part_id']],
            rule_applied='DEFAULT_PASS_THROUGH'
        )
        self.db.insert_mbom_part(line)
        return [line]

    def transform(self, root_assembly_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute the full eBOM → mBOM transformation pipeline.

        Args:
            root_assembly_id: If provided, only transform this assembly tree.
                             If None, transform all eBOM parts.

        Returns:
            Summary statistics of the transformation run.
        """
        # Reset state
        self.db.clear_mbom_and_audit()
        self._build_sequence_counter = 0
        self._audit_entries = []
        self._unmapped_parts = []

        # Load rules and parts
        rules = self.db.get_active_rules()
        if root_assembly_id:
            parts = self.db.get_ebom_tree(root_assembly_id)
        else:
            parts = self.db.get_all_ebom_parts()

        # Track which parts have been processed and merged
        processed_parts = set()
        already_merged = set()

        # Phase 1: Apply transformation rules
        for part in parts:
            part_id = part['part_id']
            if part_id in processed_parts or part_id in already_merged:
                continue

            matched = False

            # Evaluate rules in priority order
            for rule in rules:
                if not self._match_rule(rule, part):
                    continue

                rule_type = rule['rule_type']
                mbom_lines = []

                if rule_type == 'exclude':
                    mbom_lines = self._apply_exclude(rule, part)
                    matched = True
                    break  # Exclude is terminal

                elif rule_type == 'split':
                    mbom_lines = self._apply_split(rule, part)
                    matched = True
                    break

                elif rule_type == 'merge':
                    mbom_lines = self._apply_merge(rule, part, parts, already_merged)
                    if mbom_lines:  # Only mark matched if merge actually happened
                        matched = True
                        break

                elif rule_type == 'add':
                    mbom_lines = self._apply_add(rule, part)
                    matched = True
                    # ADD is additive — don't break, let other rules also fire

                elif rule_type == 'requantify':
                    mbom_lines = self._apply_requantify(rule, part)
                    matched = True
                    break

            if matched:
                processed_parts.add(part_id)
            else:
                # No rule matched — flag for human review (CRITICAL: don't silently drop)
                self._unmapped_parts.append(part)
                self.db.insert_unmapped_part(
                    unmapped_id=self._generate_id("UNM"),
                    ebom_part_id=part_id,
                    part_name=part['part_name'],
                    part_type=part['part_type'],
                    parent_assembly_id=part.get('parent_assembly_id'),
                    flag_reason="No matching transformation rule found"
                )
                # Still pass through as default
                self._apply_default_pass_through(part)
                processed_parts.add(part_id)

        # Phase 2: Run validation
        validator = ValidationLayer(self.db)
        validation_results = validator.validate_all()

        # Return summary
        summary = self.db.get_transformation_summary()
        summary['validation'] = {
            'total_checks': len(validation_results),
            'errors': sum(1 for r in validation_results if r.severity == ValidationSeverity.ERROR),
            'warnings': sum(1 for r in validation_results if r.severity == ValidationSeverity.WARNING),
            'infos': sum(1 for r in validation_results if r.severity == ValidationSeverity.INFO)
        }
        summary['unmapped_count'] = len(self._unmapped_parts)
        summary['rules_evaluated'] = len(rules)
        summary['parts_processed'] = len(processed_parts)

        return summary


class ValidationLayer:
    """
    Post-transformation validation layer.

    Business rules:
      1. Every mBOM line must have valid UOM and positive quantity
      2. Every manufactured/purchased part must map to exactly one build sequence
      3. No orphaned parent references
      4. Flag unmapped parts (handled by engine)
    """

    def __init__(self, db: Database):
        self.db = db

    def _generate_id(self) -> str:
        return f"VAL{uuid.uuid4().hex[:12].upper()}"

    def validate_all(self) -> List[ValidationResult]:
        """Run all validation rules and store results."""
        results = []
        results.extend(self._validate_uom_and_quantity())
        results.extend(self._validate_build_sequence())
        results.extend(self._validate_orphaned_parents())
        results.extend(self._validate_unmapped_parts())

        for result in results:
            self.db.insert_validation_result(result)

        return results

    def _validate_uom_and_quantity(self) -> List[ValidationResult]:
        """Rule 1: Valid UOM and positive quantity."""
        results = []
        mbom_parts = self.db.get_all_mbom_parts()

        valid_uoms = {'EA', 'M', 'KG', 'L', 'MM', 'SET', 'KIT', 'M2', 'M3', 'G', 'ML'}

        for part in mbom_parts:
            issues = []
            if part['unit_of_measure'] not in valid_uoms:
                issues.append(f"Invalid UOM: {part['unit_of_measure']}")
            if part['quantity_per_unit'] <= 0:
                issues.append(f"Non-positive quantity: {part['quantity_per_unit']}")

            if issues:
                results.append(ValidationResult(
                    validation_id=self._generate_id(),
                    rule_name="UOM_AND_QUANTITY_CHECK",
                    severity=ValidationSeverity.ERROR,
                    message="; ".join(issues),
                    affected_mbom_line_ids=[part['mbom_line_id']],
                    affected_ebom_part_ids=json.loads(part.get('source_ebom_part_ids', '[]')),
                    suggestion="Review part definition and transformation rule parameters"
                ))

        return results

    def _validate_build_sequence(self) -> List[ValidationResult]:
        """Rule 2: Every manufactured/purchased part must have a build sequence."""
        results = []
        mbom_parts = self.db.get_all_mbom_parts()

        for part in mbom_parts:
            if part['build_sequence'] is None or part['build_sequence'] <= 0:
                results.append(ValidationResult(
                    validation_id=self._generate_id(),
                    rule_name="BUILD_SEQUENCE_CHECK",
                    severity=ValidationSeverity.ERROR,
                    message=f"Missing or invalid build sequence for {part['part_id']}",
                    affected_mbom_line_ids=[part['mbom_line_id']],
                    affected_ebom_part_ids=json.loads(part.get('source_ebom_part_ids', '[]')),
                    suggestion="Assign a valid build sequence in transformation rule"
                ))

        return results

    def _validate_orphaned_parents(self) -> List[ValidationResult]:
        """Rule 3: No orphaned parent references in mBOM."""
        results = []
        mbom_parts = self.db.get_all_mbom_parts()
        mbom_part_ids = {p['part_id'] for p in mbom_parts}

        for part in mbom_parts:
            parent = part.get('parent_assembly_id')
            if parent and parent not in mbom_part_ids:
                # Check if parent exists in eBOM (it might be an assembly not in mBOM)
                ebom_parent = self.db.get_ebom_part(parent)
                if ebom_parent:
                    results.append(ValidationResult(
                        validation_id=self._generate_id(),
                        rule_name="ORPHANED_PARENT_CHECK",
                        severity=ValidationSeverity.WARNING,
                        message=f"Parent assembly {parent} exists in eBOM but not in mBOM",
                        affected_mbom_line_ids=[part['mbom_line_id']],
                        affected_ebom_part_ids=[part['part_id']],
                        suggestion="Verify if parent assembly should be included in mBOM or if child should be re-parented"
                    ))

        return results

    def _validate_unmapped_parts(self) -> List[ValidationResult]:
        """Rule 4: Flag unmapped parts for human review."""
        results = []
        unmapped = self.db.get_unmapped_parts()

        for part in unmapped:
            results.append(ValidationResult(
                validation_id=self._generate_id(),
                rule_name="UNMAPPED_PART_CHECK",
                severity=ValidationSeverity.WARNING,
                message=f"eBOM part {part['ebom_part_id']} ({part['part_name']}) has no matching transformation rule",
                affected_mbom_line_ids=[],
                affected_ebom_part_ids=[part['ebom_part_id']],
                suggestion="Create a transformation rule or mark as intentionally unmapped"
            ))

        return results
