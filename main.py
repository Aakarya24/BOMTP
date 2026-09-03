"""
================================================================================
Main Pipeline & CLI Interface
================================================================================

Usage:
  python main.py init              — Initialize database with sample data
  python main.py transform         — Run eBOM → mBOM transformation
  python main.py report            — Generate transformation report
  python main.py validate          — Run validation checks
  python main.py audit             — Display full audit trail
  python main.py export [format]   — Export mBOM (json/csv)
  python main.py test              — Run full test suite
  python main.py demo              — Run complete demo pipeline
"""

import sys
import json
import csv
import os
from datetime import datetime
from typing import List, Dict, Any

from models import *
from database import Database
from transformation_engine import TransformationEngine
from sample_data import initialize_database
import test_suite


def print_header(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def print_table(headers: List[str], rows: List[List[str]], max_width: int = 100):
    """Print a formatted table."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)[:max_width]))

    # Header
    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    print(header_line)
    print("-" * len(header_line))

    # Rows
    for row in rows:
        print(" | ".join(str(cell)[:max_width].ljust(col_widths[i]) for i, cell in enumerate(row)))


def cmd_init():
    """Initialize database with sample data."""
    print_header("Initializing Database")
    db = initialize_database()

    print(f"✓ Database: {db.db_path}")
    print(f"✓ Work centers: {len(db.get_work_centers())}")
    print(f"✓ eBOM parts: {len(db.get_all_ebom_parts())}")
    print(f"✓ Transformation rules: {len(db.get_all_rules())}")
    print("\nDatabase initialized successfully.")


def cmd_transform():
    """Run the transformation pipeline."""
    print_header("eBOM → mBOM Transformation Pipeline")

    db = Database()
    engine = TransformationEngine(db)
    summary = engine.transform()

    print(f"\n📊 Transformation Summary")
    print(f"   eBOM parts processed:     {summary['ebom_parts']}")
    print(f"   mBOM lines generated:     {summary['mbom_lines']}")
    print(f"   Audit entries created:    {summary['audit_entries']}")
    print(f"   Unmapped parts flagged:   {summary['unmapped_count']}")
    print(f"   Rules evaluated:          {summary['rules_evaluated']}")

    print(f"\n📋 Source Type Breakdown")
    for source_type, count in summary['source_breakdown'].items():
        print(f"   {source_type:25s} {count:4d}")

    print(f"\n✅ Validation Results")
    val = summary['validation']
    print(f"   Total checks:   {val['total_checks']}")
    print(f"   Errors:         {val['errors']}")
    print(f"   Warnings:       {val['warnings']}")
    print(f"   Infos:          {val['infos']}")

    if val['errors'] == 0:
        print("\n🎉 All validations passed!")
    else:
        print(f"\n⚠️  {val['errors']} validation errors found. Run 'validate' for details.")


def cmd_report():
    """Generate a detailed transformation report."""
    print_header("Transformation Report")

    db = Database()

    # eBOM overview
    ebom = db.get_all_ebom_parts()
    print(f"\n📐 eBOM Overview ({len(ebom)} parts)")
    headers = ["Part ID", "Name", "Type", "Qty", "UOM", "Parent"]
    rows = [[
        p['part_id'][:20],
        p['part_name'][:25],
        p['part_type'],
        str(p['quantity_per_parent']),
        p['unit_of_measure'],
        p.get('parent_assembly_id', '-')[:15]
    ] for p in ebom]
    print_table(headers, rows)

    # mBOM overview
    mbom = db.get_all_mbom_parts()
    print(f"\n\n🏭 mBOM Overview ({len(mbom)} lines)")
    headers = ["Line ID", "Part ID", "Name", "Qty", "Seq", "Work Center", "Source"]
    rows = [[
        m['mbom_line_id'][:12],
        m['part_id'][:18],
        m['part_name'][:22],
        str(m['quantity_per_unit']),
        str(m['build_sequence']),
        m['work_center'][:12],
        m['source_type'][:18]
    ] for m in mbom]
    print_table(headers, rows)


def cmd_validate():
    """Run and display validation results."""
    print_header("Validation Results")

    db = Database()
    results = db.get_validation_results()

    if not results:
        print("\n✅ No validation issues found.")
        return

    headers = ["Severity", "Rule", "Message", "Suggestion"]
    rows = [[
        r['severity'].upper(),
        r['rule_name'][:20],
        r['message'][:50],
        (r.get('suggestion') or '-')[:40]
    ] for r in results]
    print_table(headers, rows)

    summary = db.get_validation_summary()
    print(f"\nSummary: {summary}")


def cmd_audit():
    """Display full audit trail."""
    print_header("Audit Trail")

    db = Database()
    audit = db.get_full_audit_trail()

    if not audit:
        print("\nNo audit entries found. Run 'transform' first.")
        return

    headers = ["Timestamp", "eBOM Part", "Rule", "Type", "Justification"]
    rows = [[
        a['transformation_timestamp'][:19],
        a.get('ebom_part_name', a['ebom_part_id'])[:20],
        a['rule_name'][:22],
        a['rule_type'][:12],
        a['justification'][:45]
    ] for a in audit[:30]]  # Show first 30
    print_table(headers, rows)

    if len(audit) > 30:
        print(f"\n... and {len(audit) - 30} more entries")


def cmd_export(format_type: str = "json"):
    """Export mBOM data."""
    print_header(f"Exporting mBOM ({format_type.upper()})")

    db = Database()
    mbom = db.get_all_mbom_parts()

    if format_type.lower() == "json":
        output_path = "mbom_export.json"
        with open(output_path, 'w') as f:
            json.dump(mbom, f, indent=2, default=str)
        print(f"✓ Exported to {output_path}")

    elif format_type.lower() == "csv":
        output_path = "mbom_export.csv"
        if mbom:
            with open(output_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=mbom[0].keys())
                writer.writeheader()
                writer.writerows(mbom)
        print(f"✓ Exported to {output_path}")
    else:
        print(f"❌ Unsupported format: {format_type}")


def cmd_test():
    """Run the full test suite."""
    print_header("Running Test Suite")
    result = test_suite.run_tests()

    if result.wasSuccessful():
        print("\n🎉 All tests passed!")
    else:
        print(f"\n❌ {len(result.failures)} failures, {len(result.errors)} errors")


def cmd_demo():
    """Run the complete demo pipeline."""
    print_header("eBOM → mBOM Transformation Platform — Demo")
    print("\nThis demo shows a complete electromechanical assembly")
    print("transformation from engineering view to manufacturing view.")

    cmd_init()
    cmd_transform()
    cmd_report()
    cmd_validate()
    cmd_audit()

    print_header("Demo Complete")
    print("\nKey takeaways:")
    print("  • Virtual parts (REF-ENV-001) are excluded from mBOM")
    print("  • Wire harness is split into individual procurement items")
    print("  • Fasteners are merged into a single kit for procurement")
    print("  • Manufacturing consumables (thermal paste, packaging) are added")
    print("  • Wire quantities are adjusted for 8% scrap rate")
    print("  • Full audit trail captures every transformation decision")
    print("  • Unmapped parts are flagged, not silently dropped")


def main():
    if len(sys.argv) < 2:
        print("""
eBOM → mBOM Transformation Platform

Usage:
  python main.py init              Initialize database with sample data
  python main.py transform         Run eBOM → mBOM transformation
  python main.py report            Generate transformation report
  python main.py validate          Run validation checks
  python main.py audit             Display full audit trail
  python main.py export [json|csv] Export mBOM data
  python main.py test              Run full test suite
  python main.py demo              Run complete demo pipeline
        """)
        return

    command = sys.argv[1].lower()

    if command == "init":
        cmd_init()
    elif command == "transform":
        cmd_transform()
    elif command == "report":
        cmd_report()
    elif command == "validate":
        cmd_validate()
    elif command == "audit":
        cmd_audit()
    elif command == "export":
        fmt = sys.argv[2] if len(sys.argv) > 2 else "json"
        cmd_export(fmt)
    elif command == "test":
        cmd_test()
    elif command == "demo":
        cmd_demo()
    else:
        print(f"Unknown command: {command}")
        print("Run 'python main.py' for usage.")


if __name__ == "__main__":
    main()
