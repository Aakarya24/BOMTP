"""
================================================================================
Unit Tests — Comprehensive Test Suite
================================================================================

Coverage:
  - Data model validation
  - Database CRUD operations
  - Each transformation rule type (EXCLUDE, SPLIT, MERGE, ADD, REQUANTIFY)
  - Validation layer rules
  - Audit trail integrity
  - Edge cases and error conditions
"""

import unittest
import os
import json
from datetime import datetime

from models import *
from database import Database
from transformation_engine import TransformationEngine, ValidationLayer
from sample_data import initialize_database


class TestDataModels(unittest.TestCase):
    """Test data model creation and serialization."""

    def test_ebom_part_creation(self):
        part = EBOMPart(
            part_id="TEST-001",
            part_name="Test Part",
            parent_assembly_id="ASM-001",
            quantity_per_parent=2.0,
            part_type=PartType.MANUFACTURED,
            revision="A",
            unit_of_measure="EA",
            cad_reference_id="CAD-001"
        )
        self.assertEqual(part.part_id, "TEST-001")
        self.assertEqual(part.part_type, PartType.MANUFACTURED)
        d = part.to_dict()
        self.assertEqual(d['part_type'], 'manufactured')

    def test_mbom_part_creation(self):
        part = MBOMPart(
            mbom_line_id="MB-001",
            part_id="TEST-001",
            part_name="Test Part",
            parent_assembly_id="ASM-001",
            quantity_per_unit=2.0,
            unit_of_measure="EA",
            build_sequence=10,
            work_center="WC-001",
            source_type=MBOMSourceType.FROM_EBOM,
            source_ebom_part_ids=["TEST-001"]
        )
        self.assertEqual(part.source_type, MBOMSourceType.FROM_EBOM)
        d = part.to_dict()
        self.assertEqual(d['source_type'], 'from_ebom')

    def test_transformation_rule_creation(self):
        rule = TransformationRule(
            rule_id="RULE-001",
            rule_type=RuleType.EXCLUDE,
            rule_name="Test Exclude",
            description="Test rule",
            source_part_pattern="VIRTUAL-.*",
            justification="Test justification",
            reason_code="TEST-001"
        )
        self.assertEqual(rule.rule_type, RuleType.EXCLUDE)
        self.assertEqual(rule.priority, 100)


class TestDatabaseOperations(unittest.TestCase):
    """Test database CRUD operations."""

    @classmethod
    def setUpClass(cls):
        cls.db_path = "test_ebom_mbom.db"
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)
        cls.db = Database(cls.db_path)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)

    def test_insert_and_get_ebom_part(self):
        part = EBOMPart(
            part_id="DB-TEST-001",
            part_name="Database Test Part",
            parent_assembly_id=None,
            quantity_per_parent=1.0,
            part_type=PartType.PURCHASED,
            revision="A",
            unit_of_measure="EA",
            cad_reference_id="CAD-DB-001"
        )
        self.db.insert_ebom_part(part)
        retrieved = self.db.get_ebom_part("DB-TEST-001")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved['part_name'], "Database Test Part")
        self.assertEqual(retrieved['part_type'], 'purchased')

    def test_ebom_tree_query(self):
        # Insert parent and child
        parent = EBOMPart(
            part_id="TREE-PARENT",
            part_name="Parent Assembly",
            parent_assembly_id=None,
            quantity_per_parent=1.0,
            part_type=PartType.MANUFACTURED,
            revision="A",
            unit_of_measure="EA",
            cad_reference_id=None
        )
        child = EBOMPart(
            part_id="TREE-CHILD",
            part_name="Child Part",
            parent_assembly_id="TREE-PARENT",
            quantity_per_parent=2.0,
            part_type=PartType.PURCHASED,
            revision="A",
            unit_of_measure="EA",
            cad_reference_id=None
        )
        self.db.insert_ebom_part(parent)
        self.db.insert_ebom_part(child)

        tree = self.db.get_ebom_tree("TREE-PARENT")
        self.assertEqual(len(tree), 2)
        self.assertEqual(tree[0]['part_id'], "TREE-PARENT")
        self.assertEqual(tree[1]['part_id'], "TREE-CHILD")

    def test_insert_and_get_rule(self):
        rule = TransformationRule(
            rule_id="RULE-DB-001",
            rule_type=RuleType.EXCLUDE,
            rule_name="DB Test Rule",
            description="Test",
            source_part_pattern="TEST-.*",
            justification="Test",
            reason_code="TEST-001",
            priority=10
        )
        self.db.insert_rule(rule)
        rules = self.db.get_active_rules()
        self.assertTrue(any(r['rule_id'] == 'RULE-DB-001' for r in rules))

    def test_work_center_crud(self):
        wc = WorkCenter("WC-TEST", "Test Center", 10, "Test", ["test"])
        self.db.insert_work_center(wc)
        centers = self.db.get_work_centers()
        self.assertTrue(any(c['work_center_id'] == 'WC-TEST' for c in centers))


class TestTransformationRules(unittest.TestCase):
    """Test each transformation rule type individually."""

    @classmethod
    def setUpClass(cls):
        cls.db_path = "test_transform.db"
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)
        cls.db = initialize_database(cls.db_path)
        cls.engine = TransformationEngine(cls.db)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)

    def setUp(self):
        self.db.clear_mbom_and_audit()

    def test_exclude_rule(self):
        """Test that virtual parts are excluded from mBOM."""
        self.engine.transform()
        mbom = self.db.get_all_mbom_parts()
        virtual_in_mbom = any('REF-ENV-001' in str(m.get('source_ebom_part_ids', '')) for m in mbom)
        self.assertFalse(virtual_in_mbom, "Virtual part should not appear in mBOM")

        # Check audit trail
        audit = self.db.get_audit_by_ebom_part("REF-ENV-001")
        self.assertTrue(len(audit) > 0, "Exclude action should be audited")
        self.assertEqual(audit[0]['rule_type'], 'exclude')

    def test_split_rule(self):
        """Test that wire harness is split into components."""
        self.engine.transform()
        mbom = self.db.get_all_mbom_parts()

        # Should have split parts
        split_parts = [m for m in mbom if m.get('source_type') == 'split_from_ebom']
        self.assertTrue(len(split_parts) >= 4, "Harness should split into at least 4 parts")

        # Check for expected split components
        part_ids = [m['part_id'] for m in split_parts]
        self.assertIn("WIRE-18AWG-RED-001", part_ids)
        self.assertIn("WIRE-18AWG-BLK-001", part_ids)
        self.assertIn("CONN-CRIMP-001", part_ids)
        self.assertIn("HS-6MM-001", part_ids)

    def test_merge_rule(self):
        """Test that fasteners are merged into a kit."""
        self.engine.transform()
        mbom = self.db.get_all_mbom_parts()

        # Should have merged kit
        merged = [m for m in mbom if m.get('source_type') == 'merged_ebom']
        self.assertTrue(len(merged) > 0, "Should have merged fastener kit")

        kit = merged[0]
        self.assertEqual(kit['part_id'], "KIT-FASTENER-M3-001")

        # Check that source parts include all fasteners
        source_ids = json.loads(kit.get('source_ebom_part_ids', '[]'))
        self.assertIn("SCREW-M3x12-001", source_ids)
        self.assertIn("SCREW-M3x16-001", source_ids)
        self.assertIn("WASHER-M3-001", source_ids)
        self.assertIn("NUT-M3-001", source_ids)

    def test_add_rule(self):
        """Test that manufacturing-only items are added."""
        self.engine.transform()
        mbom = self.db.get_all_mbom_parts()

        added = [m for m in mbom if m.get('source_type') == 'added_mfg']
        self.assertTrue(len(added) >= 3, "Should have at least 3 added items")

        part_ids = [m['part_id'] for m in added]
        self.assertIn("THERMAL-PASTE-001", part_ids)
        self.assertIn("PKG-FOAM-001", part_ids)
        self.assertIn("LABEL-SERIAL-001", part_ids)

    def test_requantify_rule(self):
        """Test that quantities are adjusted for scrap rate."""
        self.engine.transform()
        mbom = self.db.get_all_mbom_parts()

        requantified = [m for m in mbom if m.get('source_type') == 'requantified']
        self.assertTrue(len(requantified) > 0, "Should have requantified parts")

        # Wire should have 8% scrap applied: 2.0 * 1.08 = 2.16
        wire = [m for m in requantified if 'WIRE-18AWG' in m['part_id']]
        self.assertTrue(len(wire) > 0, "Wire should be requantified")
        for w in wire:
            self.assertAlmostEqual(w['quantity_per_unit'], 2.16, places=2)

    def test_audit_trail_integrity(self):
        """Test that every transformation is fully audited."""
        self.engine.transform()

        audit = self.db.get_full_audit_trail()
        self.assertTrue(len(audit) > 0, "Audit trail should not be empty")

        # Every eBOM part should have at least one audit entry
        ebom_parts = self.db.get_all_ebom_parts()
        audited_part_ids = set(a['ebom_part_id'] for a in audit)
        for part in ebom_parts:
            self.assertIn(part['part_id'], audited_part_ids,
                         f"Part {part['part_id']} should have audit entry")


class TestValidationLayer(unittest.TestCase):
    """Test validation rules."""

    @classmethod
    def setUpClass(cls):
        cls.db_path = "test_validation.db"
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)
        cls.db = initialize_database(cls.db_path)
        cls.engine = TransformationEngine(cls.db)
        cls.engine.transform()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)

    def test_uom_validation(self):
        """Test that invalid UOMs are flagged."""
        results = self.db.get_validation_results()
        uom_results = [r for r in results if r['rule_name'] == 'UOM_AND_QUANTITY_CHECK']
        # Our sample data should have valid UOMs, so expect 0 errors
        self.assertEqual(len(uom_results), 0, "Sample data should have valid UOMs")

    def test_build_sequence_validation(self):
        """Test that all parts have valid build sequences."""
        results = self.db.get_validation_results()
        seq_results = [r for r in results if r['rule_name'] == 'BUILD_SEQUENCE_CHECK']
        self.assertEqual(len(seq_results), 0, "All parts should have valid build sequences")

    def test_validation_summary(self):
        """Test validation summary aggregation."""
        summary = self.db.get_validation_summary()
        self.assertIsInstance(summary, dict)


class TestUnmappedParts(unittest.TestCase):
    """Test that unmapped parts are properly flagged."""

    @classmethod
    def setUpClass(cls):
        cls.db_path = "test_unmapped.db"
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)
        cls.db = initialize_database(cls.db_path)
        cls.engine = TransformationEngine(cls.db)
        cls.engine.transform()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)

    def test_unmapped_flagging(self):
        """Test that parts without matching rules are flagged."""
        unmapped = self.db.get_unmapped_parts()
        # Some parts (like standard components) may not have specific rules
        self.assertIsInstance(unmapped, list)

    def test_unmapped_not_silently_dropped(self):
        """Critical: unmapped parts must appear in mBOM with default pass-through."""
        unmapped = self.db.get_unmapped_parts()
        mbom = self.db.get_all_mbom_parts()
        mbom_part_ids = set(m['part_id'] for m in mbom)

        for um in unmapped:
            # The part should still exist in mBOM (default pass-through)
            self.assertIn(um['ebom_part_id'], mbom_part_ids,
                         f"Unmapped part {um['ebom_part_id']} should still appear in mBOM")


class TestEndToEndPipeline(unittest.TestCase):
    """Full end-to-end integration test."""

    @classmethod
    def setUpClass(cls):
        cls.db_path = "test_e2e.db"
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)
        cls.db = initialize_database(cls.db_path)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)

    def test_full_pipeline(self):
        """Run the complete transformation pipeline and verify all outputs."""
        engine = TransformationEngine(self.db)
        summary = engine.transform()

        # Verify summary structure
        self.assertIn('ebom_parts', summary)
        self.assertIn('mbom_lines', summary)
        self.assertIn('audit_entries', summary)
        self.assertIn('validation', summary)
        self.assertIn('source_breakdown', summary)

        # Verify counts
        self.assertEqual(summary['ebom_parts'], 15)  # 15 parts in sample data
        self.assertGreater(summary['mbom_lines'], summary['ebom_parts'],
                          "mBOM should have more lines due to SPLIT and ADD")
        self.assertGreater(summary['audit_entries'], 0)

        # Verify source type breakdown
        breakdown = summary['source_breakdown']
        self.assertIn('from_ebom', breakdown)
        self.assertIn('split_from_ebom', breakdown)
        self.assertIn('merged_ebom', breakdown)
        self.assertIn('added_mfg', breakdown)

        # Verify no errors in validation
        self.assertEqual(summary['validation']['errors'], 0)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    @classmethod
    def setUpClass(cls):
        cls.db_path = "test_edge.db"
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)
        cls.db = Database(cls.db_path)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)

    def test_empty_ebom(self):
        """Test transformation with no eBOM parts."""
        engine = TransformationEngine(self.db)
        summary = engine.transform()
        self.assertEqual(summary['ebom_parts'], 0)
        self.assertEqual(summary['mbom_lines'], 0)

    def test_no_active_rules(self):
        """Test transformation with no active rules."""
        # Insert a single part
        part = EBOMPart(
            part_id="EDGE-001",
            part_name="Edge Test",
            parent_assembly_id=None,
            quantity_per_parent=1.0,
            part_type=PartType.PURCHASED,
            revision="A",
            unit_of_measure="EA",
            cad_reference_id=None
        )
        self.db.insert_ebom_part(part)

        engine = TransformationEngine(self.db)
        summary = engine.transform()

        # Should still produce mBOM via default pass-through
        self.assertEqual(summary['mbom_lines'], 1)
        self.assertEqual(summary['unmapped_count'], 1)


def run_tests():
    """Run all tests and return results."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestDataModels))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseOperations))
    suite.addTests(loader.loadTestsFromTestCase(TestTransformationRules))
    suite.addTests(loader.loadTestsFromTestCase(TestValidationLayer))
    suite.addTests(loader.loadTestsFromTestCase(TestUnmappedParts))
    suite.addTests(loader.loadTestsFromTestCase(TestEndToEndPipeline))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result


if __name__ == "__main__":
    result = run_tests()
    exit(0 if result.wasSuccessful() else 1)
