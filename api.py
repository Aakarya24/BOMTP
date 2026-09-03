"""
================================================================================
API Layer — FastAPI Application
================================================================================

Exposes the transformation pipeline as REST endpoints:
  POST /api/v1/transform          — Submit eBOM → get mBOM + audit report
  GET  /api/v1/ebom               — List all eBOM parts
  GET  /api/v1/mbom               — List all mBOM lines
  GET  /api/v1/audit              — Full audit trail
  GET  /api/v1/validation         — Validation results
  GET  /api/v1/summary            — Transformation summary
  GET  /api/v1/rules              — List transformation rules
  GET  /api/v1/work-centers       — List work centers
  GET  /api/v1/unmapped           — Unmapped parts (human review queue)
  POST /api/v1/rules              — Create new transformation rule
  PUT  /api/v1/rules/{id}         — Update transformation rule
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import uvicorn

from models import *
from database import Database
from transformation_engine import TransformationEngine
from sample_data import initialize_database


app = FastAPI(
    title="eBOM → mBOM Transformation Platform",
    description="Enterprise-grade PLM/PDM data transformation engine for manufacturing BOM generation",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global database instance (in production, use dependency injection)
db = initialize_database()


# ── Pydantic Models ─────────────────────────────────────────

class TransformRequest(BaseModel):
    root_assembly_id: Optional[str] = Field(None, description="Root assembly to transform. If null, transforms all.")


class TransformResponse(BaseModel):
    success: bool
    summary: Dict[str, Any]
    message: str


class EBOMPartResponse(BaseModel):
    part_id: str
    part_name: str
    parent_assembly_id: Optional[str]
    quantity_per_parent: float
    part_type: str
    revision: str
    unit_of_measure: str
    cad_reference_id: Optional[str]
    material_spec: Optional[str]
    drawing_number: Optional[str]


class MBOMPartResponse(BaseModel):
    mbom_line_id: str
    part_id: str
    part_name: str
    parent_assembly_id: Optional[str]
    quantity_per_unit: float
    unit_of_measure: str
    build_sequence: int
    work_center: str
    source_type: str
    source_ebom_part_ids: Optional[str]
    rule_applied: Optional[str]
    lead_time_days: Optional[int]
    supplier_id: Optional[str]


class AuditEntryResponse(BaseModel):
    audit_id: str
    ebom_part_id: str
    ebom_part_name: Optional[str]
    ebom_part_type: Optional[str]
    rule_id: str
    rule_type: str
    rule_name: str
    justification: str
    reason_code: str
    transformation_timestamp: str


class ValidationResultResponse(BaseModel):
    validation_id: str
    rule_name: str
    severity: str
    message: str
    affected_mbom_line_ids: Optional[str]
    affected_ebom_part_ids: Optional[str]
    suggestion: Optional[str]
    timestamp: str


class RuleCreateRequest(BaseModel):
    rule_type: str
    rule_name: str
    description: str
    source_part_pattern: str
    source_part_type_filter: Optional[str] = None
    parent_assembly_filter: Optional[str] = None
    target_mappings: List[Dict[str, Any]] = []
    justification: str
    reason_code: str
    priority: int = 100


class UnmappedPartResponse(BaseModel):
    unmapped_id: str
    ebom_part_id: str
    part_name: str
    part_type: str
    parent_assembly_id: Optional[str]
    flag_reason: str
    flagged_at: str


# ── API Endpoints ───────────────────────────────────────────

@app.post("/api/v1/transform", response_model=TransformResponse)
async def transform_bom(request: TransformRequest):
    """
    Execute the eBOM → mBOM transformation pipeline.

    This is the core endpoint that:
      1. Loads all eBOM parts and active transformation rules
      2. Applies rules in priority order
      3. Generates mBOM with full traceability
      4. Runs validation layer
      5. Returns summary statistics
    """
    try:
        engine = TransformationEngine(db)
        summary = engine.transform(request.root_assembly_id)
        return TransformResponse(
            success=True,
            summary=summary,
            message="Transformation completed successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/ebom", response_model=List[EBOMPartResponse])
async def get_ebom_parts(
    part_type: Optional[str] = Query(None, description="Filter by part type"),
    parent_assembly: Optional[str] = Query(None, description="Filter by parent assembly")
):
    """List all eBOM parts with optional filtering."""
    parts = db.get_all_ebom_parts()
    if part_type:
        parts = [p for p in parts if p['part_type'] == part_type]
    if parent_assembly:
        parts = [p for p in parts if p.get('parent_assembly_id') == parent_assembly]
    return [EBOMPartResponse(**p) for p in parts]


@app.get("/api/v1/ebom/{part_id}")
async def get_ebom_part(part_id: str):
    """Get a specific eBOM part by ID."""
    part = db.get_ebom_part(part_id)
    if not part:
        raise HTTPException(status_code=404, detail=f"Part {part_id} not found")
    return part


@app.get("/api/v1/ebom/tree/{root_id}")
async def get_ebom_tree(root_id: str):
    """Get the full BOM tree starting from a root assembly (recursive CTE)."""
    tree = db.get_ebom_tree(root_id)
    if not tree:
        raise HTTPException(status_code=404, detail=f"Assembly {root_id} not found")
    return tree


@app.get("/api/v1/mbom", response_model=List[MBOMPartResponse])
async def get_mbom_parts(
    work_center: Optional[str] = Query(None, description="Filter by work center"),
    source_type: Optional[str] = Query(None, description="Filter by source type")
):
    """List all mBOM lines with optional filtering."""
    if work_center:
        parts = db.get_mbom_by_work_center(work_center)
    else:
        parts = db.get_all_mbom_parts()
    if source_type:
        parts = [p for p in parts if p.get('source_type') == source_type]
    return [MBOMPartResponse(**p) for p in parts]


@app.get("/api/v1/audit", response_model=List[AuditEntryResponse])
async def get_audit_trail(
    ebom_part_id: Optional[str] = Query(None, description="Filter by eBOM part ID")
):
    """Get the full audit trail of all transformations."""
    if ebom_part_id:
        entries = db.get_audit_by_ebom_part(ebom_part_id)
    else:
        entries = db.get_full_audit_trail()
    return [AuditEntryResponse(**e) for e in entries]


@app.get("/api/v1/validation", response_model=List[ValidationResultResponse])
async def get_validation_results():
    """Get all validation results from the last transformation run."""
    results = db.get_validation_results()
    return [ValidationResultResponse(**r) for r in results]


@app.get("/api/v1/validation/summary")
async def get_validation_summary():
    """Get a summary count of validation results by severity."""
    return db.get_validation_summary()


@app.get("/api/v1/summary")
async def get_transformation_summary():
    """Get the latest transformation execution summary."""
    return db.get_transformation_summary()


@app.get("/api/v1/rules")
async def get_rules(active_only: bool = Query(False, description="Only return active rules")):
    """List all transformation rules."""
    if active_only:
        return db.get_active_rules()
    return db.get_all_rules()


@app.post("/api/v1/rules")
async def create_rule(request: RuleCreateRequest):
    """Create a new transformation rule."""
    import uuid
    rule = TransformationRule(
        rule_id=f"RULE-{uuid.uuid4().hex[:8].upper()}",
        rule_type=RuleType(request.rule_type),
        rule_name=request.rule_name,
        description=request.description,
        source_part_pattern=request.source_part_pattern,
        source_part_type_filter=PartType(request.source_part_type_filter) if request.source_part_type_filter else None,
        parent_assembly_filter=request.parent_assembly_filter,
        target_mappings=request.target_mappings,
        justification=request.justification,
        reason_code=request.reason_code,
        priority=request.priority,
        is_active=True
    )
    db.insert_rule(rule)
    return {"success": True, "rule_id": rule.rule_id}


@app.get("/api/v1/work-centers")
async def get_work_centers():
    """List all manufacturing work centers."""
    return db.get_work_centers()


@app.get("/api/v1/unmapped", response_model=List[UnmappedPartResponse])
async def get_unmapped_parts():
    """Get parts flagged for human review (no matching rule)."""
    parts = db.get_unmapped_parts()
    return [UnmappedPartResponse(**p) for p in parts]


@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "database": db.db_path
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
