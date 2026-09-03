"""
================================================================================
Data Models & Database Schema
================================================================================
Enterprise-grade eBOM → mBOM Data Transformation Platform
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum, auto
from typing import Optional, List, Dict, Any, Tuple
import json


class PartType(Enum):
    """Classification of part types in the engineering domain."""
    MANUFACTURED = "manufactured"
    PURCHASED = "purchased"
    VIRTUAL = "virtual"
    REFERENCE = "reference"
    STANDARD = "standard"
    FASTENER = "fastener"


class MBOMSourceType(Enum):
    """Traceability: where did this mBOM line come from?"""
    FROM_EBOM = "from_ebom"
    ADDED_FOR_MANUFACTURING = "added_mfg"
    SPLIT_FROM_EBOM = "split_from_ebom"
    MERGED_EBOM = "merged_ebom"
    REQUANTIFIED = "requantified"


class RuleType(Enum):
    """The five core transformation rule types."""
    EXCLUDE = "exclude"
    SPLIT = "split"
    MERGE = "merge"
    ADD = "add"
    REQUANTIFY = "requantify"


class ValidationSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class EBOMPart:
    """Engineering Bill of Materials Part — designer's view."""
    part_id: str
    part_name: str
    parent_assembly_id: Optional[str]
    quantity_per_parent: float
    part_type: PartType
    revision: str
    unit_of_measure: str
    cad_reference_id: Optional[str]
    material_spec: Optional[str] = None
    drawing_number: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['part_type'] = self.part_type.value
        d['created_at'] = self.created_at.isoformat()
        return d


@dataclass
class MBOMPart:
    """Manufacturing Bill of Materials Part — factory's view."""
    mbom_line_id: str
    part_id: str
    part_name: str
    parent_assembly_id: Optional[str]
    quantity_per_unit: float
    unit_of_measure: str
    build_sequence: int
    work_center: str
    source_type: MBOMSourceType
    source_ebom_part_ids: List[str]
    rule_applied: Optional[str] = None
    lead_time_days: Optional[int] = None
    supplier_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['source_type'] = self.source_type.value
        d['created_at'] = self.created_at.isoformat()
        return d


@dataclass
class TransformationRule:
    """Configurable rule defining eBOM → mBOM mapping."""
    rule_id: str
    rule_type: RuleType
    rule_name: str
    description: str
    source_part_pattern: str
    justification: str
    reason_code: str
    source_part_type_filter: Optional[PartType] = None
    parent_assembly_filter: Optional[str] = None
    target_mappings: List[Dict[str, Any]] = field(default_factory=list)
    priority: int = 100
    is_active: bool = True
    created_by: str = "system"
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['rule_type'] = self.rule_type.value
        d['source_part_type_filter'] = self.source_part_type_filter.value if self.source_part_type_filter else None
        d['created_at'] = self.created_at.isoformat()
        return d


@dataclass
class AuditEntry:
    """Full traceability record for every transformation decision."""
    audit_id: str
    ebom_part_id: str
    rule_id: str
    rule_type: RuleType
    rule_name: str
    justification: str
    reason_code: str
    ebom_state: Dict[str, Any] = field(default_factory=dict)
    mbom_lines_created: List[Dict[str, Any]] = field(default_factory=list)
    mbom_lines_modified: List[Dict[str, Any]] = field(default_factory=list)
    transformation_timestamp: datetime = field(default_factory=datetime.utcnow)
    processed_by: str = "transformation_engine_v1"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['rule_type'] = self.rule_type.value
        d['transformation_timestamp'] = self.transformation_timestamp.isoformat()
        return d


@dataclass
class ValidationResult:
    """Outcome of a validation rule check against generated mBOM."""
    validation_id: str
    rule_name: str
    severity: ValidationSeverity
    message: str
    affected_mbom_line_ids: List[str] = field(default_factory=list)
    affected_ebom_part_ids: List[str] = field(default_factory=list)
    suggestion: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['severity'] = self.severity.value
        d['timestamp'] = self.timestamp.isoformat()
        return d


@dataclass
class WorkCenter:
    """Manufacturing station / work cell definition."""
    work_center_id: str
    work_center_name: str
    station_number: int
    description: str
    capabilities: List[str] = field(default_factory=list)
