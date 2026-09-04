"""
================================================================================
Database Layer — SQLite with Full Enterprise Schema
================================================================================

Schema designed for:
  - Full referential integrity
  - Efficient querying of BOM hierarchies
  - Audit trail compliance
  - Rule-based transformation lookups
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager
from models import *


SCHEMA_SQL = """
-- ============================================================
-- eBOM → mBOM Transformation Platform Schema
-- ============================================================

-- Work Centers / Manufacturing Stations
CREATE TABLE IF NOT EXISTS work_centers (
    work_center_id      TEXT PRIMARY KEY,
    work_center_name    TEXT NOT NULL,
    station_number      INTEGER NOT NULL,
    description         TEXT,
    capabilities        TEXT,              -- JSON array
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Engineering BOM Parts
CREATE TABLE IF NOT EXISTS ebom_parts (
    part_id             TEXT PRIMARY KEY,
    part_name           TEXT NOT NULL,
    parent_assembly_id  TEXT,
    quantity_per_parent REAL NOT NULL,
    part_type           TEXT NOT NULL,      -- manufactured/purchased/virtual/reference/standard/fastener
    revision            TEXT NOT NULL,
    unit_of_measure     TEXT NOT NULL,
    cad_reference_id    TEXT,
    material_spec       TEXT,
    drawing_number      TEXT,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_assembly_id) REFERENCES ebom_parts(part_id)
);

-- Manufacturing BOM Parts
CREATE TABLE IF NOT EXISTS mbom_parts (
    mbom_line_id        TEXT PRIMARY KEY,
    part_id             TEXT NOT NULL,
    part_name           TEXT NOT NULL,
    parent_assembly_id  TEXT,
    quantity_per_unit   REAL NOT NULL,
    unit_of_measure     TEXT NOT NULL,
    build_sequence      INTEGER NOT NULL,
    work_center         TEXT NOT NULL,
    source_type         TEXT NOT NULL,      -- from_ebom/added_mfg/split_from_ebom/merged_ebom/requantified
    source_ebom_part_ids TEXT,              -- JSON array
    rule_applied        TEXT,
    lead_time_days      INTEGER,
    supplier_id         TEXT,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_center) REFERENCES work_centers(work_center_id)
);

-- Transformation Rules
CREATE TABLE IF NOT EXISTS transformation_rules (
    rule_id             TEXT PRIMARY KEY,
    rule_type           TEXT NOT NULL,      -- exclude/split/merge/add/requantify
    rule_name           TEXT NOT NULL,
    description         TEXT,
    source_part_pattern TEXT NOT NULL,
    source_part_type_filter TEXT,
    parent_assembly_filter TEXT,
    target_mappings     TEXT,               -- JSON
    justification       TEXT NOT NULL,
    reason_code         TEXT NOT NULL,
    priority            INTEGER DEFAULT 100,
    is_active           INTEGER DEFAULT 1,
    created_by          TEXT DEFAULT 'system',
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Audit Log — Full Traceability
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id            TEXT PRIMARY KEY,
    ebom_part_id        TEXT NOT NULL,
    rule_id             TEXT NOT NULL,
    rule_type           TEXT NOT NULL,
    rule_name           TEXT NOT NULL,
    ebom_state          TEXT,               -- JSON snapshot
    mbom_lines_created  TEXT,               -- JSON array
    mbom_lines_modified TEXT,               -- JSON array
    justification       TEXT NOT NULL,
    reason_code         TEXT NOT NULL,
    transformation_timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    processed_by        TEXT DEFAULT 'transformation_engine_v1'
);

-- Validation Results
CREATE TABLE IF NOT EXISTS validation_results (
    validation_id       TEXT PRIMARY KEY,
    rule_name           TEXT NOT NULL,
    severity            TEXT NOT NULL,      -- error/warning/info
    message             TEXT NOT NULL,
    affected_mbom_line_ids TEXT,            -- JSON array
    affected_ebom_part_ids TEXT,             -- JSON array
    suggestion          TEXT,
    timestamp           TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Unmapped Parts (flagged for human review)
CREATE TABLE IF NOT EXISTS unmapped_parts (
    unmapped_id         TEXT PRIMARY KEY,
    ebom_part_id        TEXT NOT NULL,
    part_name           TEXT NOT NULL,
    part_type           TEXT NOT NULL,
    parent_assembly_id  TEXT,
    flag_reason         TEXT NOT NULL,
    flagged_at          TEXT DEFAULT CURRENT_TIMESTAMP,
    resolved            INTEGER DEFAULT 0,
    resolved_by         TEXT,
    resolution_note     TEXT
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_ebom_parent ON ebom_parts(parent_assembly_id);
CREATE INDEX IF NOT EXISTS idx_ebom_type ON ebom_parts(part_type);
CREATE INDEX IF NOT EXISTS idx_mbom_workcenter ON mbom_parts(work_center);
CREATE INDEX IF NOT EXISTS idx_mbom_buildseq ON mbom_parts(build_sequence);
CREATE INDEX IF NOT EXISTS idx_audit_ebom ON audit_log(ebom_part_id);
CREATE INDEX IF NOT EXISTS idx_audit_rule ON audit_log(rule_id);
CREATE INDEX IF NOT EXISTS idx_rules_active ON transformation_rules(is_active, priority);
CREATE INDEX IF NOT EXISTS idx_unmapped_resolved ON unmapped_parts(resolved);
"""


class Database:
    """Enterprise-grade SQLite database manager with connection pooling."""

    def __init__(self, db_path: str = "ebom_mbom.db"):
        self.db_path = db_path
        self._init_schema()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _init_schema(self):
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)

    # ── CRUD: eBOM Parts ──────────────────────────────────────

    def insert_ebom_part(self, part: EBOMPart) -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO ebom_parts 
                (part_id, part_name, parent_assembly_id, quantity_per_parent,
                 part_type, revision, unit_of_measure, cad_reference_id,
                 material_spec, drawing_number, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                part.part_id, part.part_name, part.parent_assembly_id,
                part.quantity_per_parent, part.part_type.value, part.revision,
                part.unit_of_measure, part.cad_reference_id, part.material_spec,
                part.drawing_number, part.created_at.isoformat()
            ))

    def get_ebom_part(self, part_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM ebom_parts WHERE part_id = ?", (part_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_all_ebom_parts(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM ebom_parts ORDER BY part_id").fetchall()
            return [dict(r) for r in rows]

    def get_ebom_tree(self, root_part_id: str) -> List[Dict[str, Any]]:
        """Recursive CTE to get full BOM tree from root."""
        with self._connect() as conn:
            rows = conn.execute("""
                WITH RECURSIVE bom_tree AS (
                    SELECT *, 0 as level FROM ebom_parts WHERE part_id = ?
                    UNION ALL
                    SELECT e.*, bt.level + 1
                    FROM ebom_parts e
                    JOIN bom_tree bt ON e.parent_assembly_id = bt.part_id
                )
                SELECT * FROM bom_tree ORDER BY level, part_id
            """, (root_part_id,)).fetchall()
            return [dict(r) for r in rows]

    # ── CRUD: Transformation Rules ──────────────────────────────

    def insert_rule(self, rule: TransformationRule) -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO transformation_rules
                (rule_id, rule_type, rule_name, description, source_part_pattern,
                 source_part_type_filter, parent_assembly_filter, target_mappings,
                 justification, reason_code, priority, is_active, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rule.rule_id, rule.rule_type.value, rule.rule_name, rule.description,
                rule.source_part_pattern,
                rule.source_part_type_filter.value if rule.source_part_type_filter else None,
                rule.parent_assembly_filter,
                json.dumps(rule.target_mappings) if rule.target_mappings else None,
                rule.justification, rule.reason_code, rule.priority,
                1 if rule.is_active else 0, rule.created_by, rule.created_at.isoformat()
            ))

    def get_active_rules(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM transformation_rules 
                WHERE is_active = 1 
                ORDER BY priority ASC, created_at ASC
            """).fetchall()
            return [dict(r) for r in rows]

    def get_all_rules(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM transformation_rules ORDER BY priority ASC").fetchall()
            return [dict(r) for r in rows]

    # ── CRUD: mBOM Parts ──────────────────────────────────────

    def insert_mbom_part(self, part: MBOMPart) -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO mbom_parts
                (mbom_line_id, part_id, part_name, parent_assembly_id, quantity_per_unit,
                 unit_of_measure, build_sequence, work_center, source_type,
                 source_ebom_part_ids, rule_applied, lead_time_days, supplier_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                part.mbom_line_id, part.part_id, part.part_name, part.parent_assembly_id,
                part.quantity_per_unit, part.unit_of_measure, part.build_sequence,
                part.work_center, part.source_type.value,
                json.dumps(part.source_ebom_part_ids) if part.source_ebom_part_ids else None,
                part.rule_applied, part.lead_time_days, part.supplier_id,
                part.created_at.isoformat()
            ))

    def get_all_mbom_parts(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM mbom_parts ORDER BY build_sequence, part_id").fetchall()
            return [dict(r) for r in rows]

    def get_mbom_by_work_center(self, work_center: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM mbom_parts WHERE work_center = ? ORDER BY build_sequence",
                (work_center,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ── CRUD: Audit Log ───────────────────────────────────────

    def insert_audit_entry(self, entry: AuditEntry) -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO audit_log
                (audit_id, ebom_part_id, rule_id, rule_type, rule_name,
                 ebom_state, mbom_lines_created, mbom_lines_modified,
                 justification, reason_code, transformation_timestamp, processed_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.audit_id, entry.ebom_part_id, entry.rule_id,
                entry.rule_type.value, entry.rule_name,
                json.dumps(entry.ebom_state) if entry.ebom_state else None,
                json.dumps(entry.mbom_lines_created) if entry.mbom_lines_created else None,
                json.dumps(entry.mbom_lines_modified) if entry.mbom_lines_modified else None,
                entry.justification, entry.reason_code,
                entry.transformation_timestamp.isoformat(), entry.processed_by
            ))

    def get_audit_by_ebom_part(self, ebom_part_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM audit_log 
                WHERE ebom_part_id = ? 
                ORDER BY transformation_timestamp DESC
            """, (ebom_part_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_full_audit_trail(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT a.*, e.part_name as ebom_part_name, e.part_type as ebom_part_type
                FROM audit_log a
                LEFT JOIN ebom_parts e ON a.ebom_part_id = e.part_id
                ORDER BY a.transformation_timestamp DESC
            """).fetchall()
            return [dict(r) for r in rows]

    # ── CRUD: Validation Results ──────────────────────────────

    def insert_validation_result(self, result: ValidationResult) -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO validation_results
                (validation_id, rule_name, severity, message,
                 affected_mbom_line_ids, affected_ebom_part_ids, suggestion, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.validation_id, result.rule_name, result.severity.value,
                result.message,
                json.dumps(result.affected_mbom_line_ids) if result.affected_mbom_line_ids else None,
                json.dumps(result.affected_ebom_part_ids) if result.affected_ebom_part_ids else None,
                result.suggestion, result.timestamp.isoformat()
            ))

    def get_validation_results(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM validation_results ORDER BY timestamp DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_validation_summary(self) -> Dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT severity, COUNT(*) as count 
                FROM validation_results 
                GROUP BY severity
            """).fetchall()
            return {r['severity']: r['count'] for r in rows}

    # ── CRUD: Unmapped Parts ──────────────────────────────────

    def insert_unmapped_part(self, unmapped_id: str, ebom_part_id: str, 
                             part_name: str, part_type: str, parent_assembly_id: Optional[str],
                             flag_reason: str) -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO unmapped_parts
                (unmapped_id, ebom_part_id, part_name, part_type, parent_assembly_id, flag_reason)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (unmapped_id, ebom_part_id, part_name, part_type, parent_assembly_id, flag_reason))

    def get_unmapped_parts(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM unmapped_parts WHERE resolved = 0 ORDER BY flagged_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    # ── CRUD: Work Centers ────────────────────────────────────

    def insert_work_center(self, wc: WorkCenter) -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO work_centers (work_center_id, work_center_name, station_number, description, capabilities)
                VALUES (?, ?, ?, ?, ?)
            """, (wc.work_center_id, wc.work_center_name, wc.station_number, 
                  wc.description, json.dumps(wc.capabilities)))

    def get_work_centers(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM work_centers ORDER BY station_number").fetchall()
            return [dict(r) for r in rows]

    # ── Utility ─────────────────────────────────────────────────

    def clear_mbom_and_audit(self) -> None:
        """Clear mBOM, audit, validation, and unmapped tables for re-run."""
        with self._connect() as conn:
            conn.execute("DELETE FROM mbom_parts")
            conn.execute("DELETE FROM audit_log")
            conn.execute("DELETE FROM validation_results")
            conn.execute("DELETE FROM unmapped_parts")

    def get_transformation_summary(self) -> Dict[str, Any]:
        """High-level pipeline execution summary."""
        with self._connect() as conn:
            ebom_count = conn.execute("SELECT COUNT(*) FROM ebom_parts").fetchone()[0]
            mbom_count = conn.execute("SELECT COUNT(*) FROM mbom_parts").fetchone()[0]
            audit_count = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            unmapped_count = conn.execute("SELECT COUNT(*) FROM unmapped_parts WHERE resolved = 0").fetchone()[0]

            source_breakdown = conn.execute("""
                SELECT source_type, COUNT(*) as count FROM mbom_parts GROUP BY source_type
            """).fetchall()

            return {
                "ebom_parts": ebom_count,
                "mbom_lines": mbom_count,
                "audit_entries": audit_count,
                "unmapped_parts": unmapped_count,
                "source_breakdown": {r['source_type']: r['count'] for r in source_breakdown}
            }
