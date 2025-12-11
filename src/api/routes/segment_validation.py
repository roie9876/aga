"""Segment-based validation API endpoints for decomposed plans."""
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from src.azure import get_cosmos_client, get_openai_client
from src.services.segment_analyzer import get_segment_analyzer
from src.services.mamad_validator import get_mamad_validator
from src.services.requirements_coverage import get_coverage_tracker
from src.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


class SegmentValidationRequest(BaseModel):
    """Request to validate approved segments."""
    decomposition_id: str = Field(..., description="Decomposition ID")
    approved_segment_ids: List[str] = Field(..., description="List of approved segment IDs to validate")


class SegmentValidationResponse(BaseModel):
    """Response from segment validation."""
    validation_id: str = Field(..., description="Validation result ID")
    total_segments: int = Field(..., description="Total segments validated")
    passed: int = Field(..., description="Segments that passed")
    failed: int = Field(..., description="Segments that failed")
    warnings: int = Field(..., description="Segments with warnings")
    analyzed_segments: List[Dict[str, Any]] = Field(default_factory=list, description="Detailed analysis for each segment")
    coverage: Optional[Dict[str, Any]] = Field(None, description="Requirements coverage report")


@router.post("/validate-segments", response_model=SegmentValidationResponse)
async def validate_segments(request: SegmentValidationRequest):
    """Validate approved segments from decomposition.
    
    This endpoint:
    1. Fetches the decomposition and approved segments
    2. For each segment, analyzes the cropped image with GPT
    3. Extracts measurements, text, and structural details
    4. Validates against ממ"ד requirements
    5. Stores validation results
    
    Args:
        request: Validation request with decomposition ID and segment IDs
        
    Returns:
        Validation summary with pass/fail counts
    """
    logger.info("Starting segment validation",
               decomposition_id=request.decomposition_id,
               segment_count=len(request.approved_segment_ids))
    
    try:
        # 1. Fetch decomposition from Cosmos DB
        cosmos_client = get_cosmos_client()
        
        query = """
            SELECT * FROM c 
            WHERE c.id = @decomposition_id 
            AND c.type = 'decomposition'
        """
        parameters = [{"name": "@decomposition_id", "value": request.decomposition_id}]
        
        results = await cosmos_client.query_items(query, parameters)
        
        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"Decomposition not found: {request.decomposition_id}"
            )
        
        decomposition = results[0]
        
        # 2. Filter approved segments
        all_segments = decomposition.get("segments", [])
        approved_segments = [
            seg for seg in all_segments 
            if seg["segment_id"] in request.approved_segment_ids
        ]
        
        if not approved_segments:
            raise HTTPException(
                status_code=400,
                detail="No approved segments found"
            )
        
        logger.info("Found approved segments",
                   total=len(all_segments),
                   approved=len(approved_segments))
        
        # 3. Analyze each segment with GPT (Part 3 - OCR + Interpretation)
        logger.info("Starting segment analysis with GPT-5.1",
                   segment_count=len(approved_segments))
        
        analyzer = get_segment_analyzer()
        validator = get_mamad_validator()
        analyzed_segments = []
        
        for segment in approved_segments:
            try:
                # Part 3: Analyze and classify segment with GPT (NO validation yet)
                analysis_result = await analyzer.analyze_segment(
                    segment_id=segment["segment_id"],
                    segment_blob_url=segment["blob_url"],
                    segment_type=segment["type"],
                    segment_description=segment["description"]
                )
                
                # Part 4: Validate ONLY if analysis was successful and has classification
                if analysis_result["status"] == "analyzed":
                    # Run targeted validation based on segment classification
                    validation_result = validator.validate_segment(
                        analysis_result.get("analysis_data", {})
                    )
                    analysis_result["validation"] = validation_result
                    
                    # Log what was found vs what was checked
                    classification = analysis_result.get("analysis_data", {}).get("classification", {})
                    logger.info("Segment analyzed and validated",
                               segment_id=segment["segment_id"],
                               classification=classification.get("primary_category"),
                               relevant_requirements=classification.get("relevant_requirements"),
                               validation_passed=validation_result.get("passed", False))
                else:
                    # Analysis failed - no validation
                    analysis_result["validation"] = {
                        "status": "skipped",
                        "passed": False,
                        "violations": []
                    }
                
                analyzed_segments.append(analysis_result)
                
            except Exception as e:
                logger.error("Failed to analyze segment",
                            segment_id=segment["segment_id"],
                            error=str(e))
                analyzed_segments.append({
                    "segment_id": segment["segment_id"],
                    "status": "error",
                    "error": str(e),
                    "validation": {
                        "status": "error",
                        "passed": False,
                        "violations": []
                    }
                })
        
        # 4. Store analysis results in Cosmos DB
        validation_id = f"val-{uuid.uuid4()}"
        
        validation_doc = {
            "id": validation_id,
            "type": "segment_validation",
            "decomposition_id": request.decomposition_id,
            "validation_id": decomposition.get("validation_id"),
            "project_id": decomposition.get("project_id"),
            "analyzed_segments": analyzed_segments,
            "created_at": "2025-12-11T00:00:00Z"  # Will be set by Cosmos
        }
        
        await cosmos_client.create_item(validation_doc)
        
        # 5. Calculate pass/fail stats based on actual validation results
        passed = sum(1 for s in analyzed_segments 
                    if s.get("validation", {}).get("passed", False))
        failed = sum(1 for s in analyzed_segments 
                    if s.get("status") == "error" or not s.get("validation", {}).get("passed", False))
        
        # Count warnings across all segments
        warnings = sum(
            s.get("validation", {}).get("warning_count", 0) 
            for s in analyzed_segments
        )
        
        # 6. Calculate requirements coverage
        tracker = get_coverage_tracker()
        coverage_report = tracker.calculate_coverage({
            "analyzed_segments": analyzed_segments
        })
        
        logger.info("Validation complete",
                   validation_id=validation_id,
                   passed=passed,
                   failed=failed,
                   warnings=warnings,
                   coverage_percentage=coverage_report["statistics"]["coverage_percentage"],
                   pass_percentage=coverage_report["statistics"]["pass_percentage"])
        
        return {
            "validation_id": validation_id,
            "total_segments": len(approved_segments),
            "passed": passed,
            "failed": failed,
            "warnings": warnings,
            "analyzed_segments": analyzed_segments,  # Include detailed analysis
            "coverage": coverage_report  # Include requirements coverage
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Segment validation failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Validation failed: {str(e)}"
        )


@router.get("/validations")
async def list_validations():
    """List all validation history.
    
    Returns:
        List of all validations sorted by date (newest first)
    """
    logger.info("Fetching validation history")
    
    try:
        cosmos_client = get_cosmos_client()
        
        # Get all validations
        query = """
            SELECT c.id, c.decomposition_id, c.validation_id, c.project_id,
                   c.total_segments, c.passed, c.failed, c.warnings, 
                   c.created_at, c.coverage
            FROM c 
            WHERE c.type = 'segment_validation'
            ORDER BY c._ts DESC
        """
        
        results = await cosmos_client.query_items(query, [])
        
        # Enrich with plan names from decomposition in batch
        decomposition_ids = list(set([r.get("decomposition_id") for r in results if r.get("decomposition_id")]))
        
        # Fetch all decompositions in one query
        decomposition_map = {}
        if decomposition_ids:
            decomp_query = f"""
                SELECT c.id, c.metadata.project_name, c.metadata.plan_number, c.created_at
                FROM c 
                WHERE c.type = 'decomposition'
                AND c.id IN ({','.join([f"'{did}'" for did in decomposition_ids])})
            """
            decomp_results = await cosmos_client.query_items(decomp_query, [])
            decomposition_map = {d["id"]: d for d in decomp_results}
        
        # Enrich results
        enriched_results = []
        for result in results:
            decomp_id = result.get("decomposition_id")
            decomp_data = decomposition_map.get(decomp_id) if decomp_id else None
            
            # Get plan name
            plan_name = "תכנית ללא שם"
            created_at = result.get("created_at", "2025-12-11T00:00:00Z")
            
            if decomp_data:
                plan_name = (
                    decomp_data.get("project_name") or 
                    decomp_data.get("plan_number") or 
                    f"תכנית {decomp_id[:8]}"
                )
                # Use decomposition created_at if available
                if decomp_data.get("created_at"):
                    created_at = decomp_data["created_at"]
            
            # Calculate status
            passed = result.get("passed", 0)
            failed = result.get("failed", 0)
            status = "pass" if failed == 0 and passed > 0 else "fail" if failed > 0 else "needs_review"
            
            enriched_results.append({
                **result,
                "plan_name": plan_name,
                "status": status,
                "created_at": created_at
            })
        
        logger.info(f"Returning {len(enriched_results)} validations")
        
        return {
            "total": len(enriched_results),
            "validations": enriched_results
        }
        
    except Exception as e:
        logger.error("Failed to fetch validation history", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch history: {str(e)}"
        )


@router.get("/validation/{validation_id}")
async def get_validation_results(validation_id: str):
    """Get detailed validation results.
    
    Args:
        validation_id: Validation ID
        
    Returns:
        Detailed validation results with per-segment analysis
    """
    logger.info("Fetching validation results", validation_id=validation_id)
    
    try:
        cosmos_client = get_cosmos_client()
        
        query = """
            SELECT * FROM c 
            WHERE c.id = @validation_id 
            AND c.type = 'segment_validation'
        """
        parameters = [{"name": "@validation_id", "value": validation_id}]
        
        results = await cosmos_client.query_items(query, parameters)
        
        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"Validation not found: {validation_id}"
            )
        
        return results[0]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch validation results", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch results: {str(e)}"
        )
