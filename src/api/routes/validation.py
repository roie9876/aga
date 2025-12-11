"""Validation API endpoints."""
import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional

from src.models import ValidationResponse, ValidationResult
from src.services import get_plan_extractor
from src.services.llm_validator import get_llm_validator
from src.azure import get_blob_client, get_cosmos_client
from src.utils.logging import get_logger
from src.utils.file_converter import convert_to_image_if_needed, is_supported_format

logger = get_logger(__name__)
router = APIRouter()


@router.post("/validate", response_model=ValidationResponse)
async def validate_plan(
    file: UploadFile = File(..., description="Architectural plan file (PDF, DWG, DWF, DWFX, PNG, JPG)"),
    project_id: str = Form(..., description="Project identifier"),
    plan_name: Optional[str] = Form(None, description="Optional plan name")
):
    """Upload and validate an architectural plan.
    
    This endpoint:
    1. Uploads the plan to Azure Blob Storage
    2. Extracts measurements using GPT-5.1 with reasoning
    3. Validates against ממד requirements
    4. Stores results in Cosmos DB
    5. Returns validation ID for retrieving full results
    
    Args:
        file: Uploaded architectural plan file
        project_id: Project identifier for grouping validations
        plan_name: Optional name for the plan (defaults to filename)
        
    Returns:
        ValidationResponse with validation ID and status
        
    Raises:
        HTTPException: If validation fails
    """
    logger.info("Received validation request", 
               project_id=project_id, 
               filename=file.filename)
    
    try:
        # Validate file format
        if not is_supported_format(file.filename):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format: {file.filename}. Supported: PDF, DWG, DWF, DWFX, PNG, JPG"
            )
        
        # Generate unique validation ID
        validation_id = str(uuid.uuid4())
        blob_name = f"{project_id}/{validation_id}/{file.filename}"
        display_name = plan_name or file.filename
        
        # Read file content
        file_content = await file.read()
        
        # Convert DWF to image if needed
        logger.info("Checking if file needs conversion", filename=file.filename)
        try:
            processed_bytes, processed_filename, was_converted = convert_to_image_if_needed(
                file_bytes=file_content,
                filename=file.filename
            )
            
            if was_converted:
                logger.info("File converted successfully", 
                           original=file.filename, 
                           converted=processed_filename)
                # Update blob name to reflect converted file
                blob_name = f"{project_id}/{validation_id}/{processed_filename}"
            else:
                processed_bytes = file_content
                processed_filename = file.filename
                
        except ValueError as e:
            logger.error("File conversion failed", error=str(e))
            raise HTTPException(status_code=400, detail=str(e))
        
        # 1. Upload to Blob Storage (use converted file if applicable)
        logger.info("Uploading plan to Blob Storage", blob_name=blob_name)
        # 1. Upload to Blob Storage (use converted file if applicable)
        logger.info("Uploading plan to Blob Storage", blob_name=blob_name)
        blob_client = get_blob_client()
        from io import BytesIO
        plan_blob_url = await blob_client.upload_blob(
            blob_name=blob_name,
            data=BytesIO(processed_bytes)
        )
        
        # 2. Extract data with GPT-5.1 (use converted file)
        logger.info("Extracting data with GPT-5.1", validation_id=validation_id)
        extractor = get_plan_extractor()
        extracted_data = await extractor.extract_from_plan(
            file_bytes=processed_bytes,
            file_name=processed_filename
        )
        
        # 3. Validate against requirements using LLM (use converted file)
        logger.info("Validating against requirements using GPT-5.1", validation_id=validation_id)
        validator = get_llm_validator()
        validation_result = validator.validate(
            validation_id=validation_id,
            project_id=project_id,
            plan_name=display_name,
            plan_blob_url=plan_blob_url,
            extracted_data=extracted_data,
            plan_image_bytes=processed_bytes  # Pass the converted image for GPT bounding boxes
        )
        
        # 4. Store results in Cosmos DB
        logger.info("Storing results in Cosmos DB", validation_id=validation_id)
        cosmos_client = get_cosmos_client()
        result_dict = validation_result.model_dump(mode='json')
        result_dict["project_id"] = project_id  # Ensure partition key is set
        await cosmos_client.create_item(result_dict)
        
        logger.info("Validation completed successfully", 
                   validation_id=validation_id,
                   status=validation_result.status.value)
        
        return ValidationResponse(
            success=True,
            validation_id=validation_id,
            message=f"תוכנית נבדקה בהצלחה. סטטוס: {validation_result.status.value}"
        )
        
    except Exception as e:
        logger.error("Validation failed", error=str(e), project_id=project_id)
        raise HTTPException(
            status_code=500,
            detail=f"אירעה שגיאה בבדיקת התוכנית: {str(e)}"
        )


@router.get("/results/{validation_id}", response_model=ValidationResult)
async def get_validation_result(validation_id: str):
    """Retrieve validation results by ID.
    
    Args:
        validation_id: Unique validation result identifier
        
    Returns:
        Complete ValidationResult with all violations and data
        
    Raises:
        HTTPException: If validation not found
    """
    logger.info("Fetching validation result", validation_id=validation_id)
    
    try:
        cosmos_client = get_cosmos_client()
        
        # Query by id across all partitions
        query = "SELECT * FROM c WHERE c.id = @validation_id"
        parameters = [{"name": "@validation_id", "value": validation_id}]
        
        results = await cosmos_client.query_items(query, parameters)
        
        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"תוצאת בדיקה לא נמצאה: {validation_id}"
            )
        
        result_dict = results[0]
        validation_result = ValidationResult(**result_dict)
        
        logger.info("Validation result retrieved", validation_id=validation_id)
        return validation_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to retrieve validation result", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"אירעה שגיאה בשליפת התוצאות: {str(e)}"
        )


@router.get("/projects/{project_id}/validations")
async def list_project_validations(project_id: str):
    """List all validations for a project.
    
    Args:
        project_id: Project identifier
        
    Returns:
        List of validation summaries for the project
    """
    logger.info("Listing validations for project", project_id=project_id)
    
    try:
        cosmos_client = get_cosmos_client()
        
        # Query by project_id partition key
        query = "SELECT c.id, c.plan_name, c.status, c.created_at, c.failed_checks FROM c WHERE c.project_id = @project_id ORDER BY c.created_at DESC"
        parameters = [{"name": "@project_id", "value": project_id}]
        
        results = await cosmos_client.query_items(query, parameters)
        
        logger.info("Retrieved validations for project", 
                   project_id=project_id,
                   count=len(results))
        
        return {
            "project_id": project_id,
            "validation_count": len(results),
            "validations": results
        }
        
    except Exception as e:
        logger.error("Failed to list validations", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"אירעה שגיאה בשליפת רשימת הבדיקות: {str(e)}"
        )


@router.get("/requirements")
async def get_requirements():
    """Get the current requirements content from requirements-mamad.md.
    
    Returns:
        Current requirements markdown content
    """
    logger.info("Fetching current requirements")
    
    try:
        from pathlib import Path
        requirements_path = Path("requirements-mamad.md")
        
        if not requirements_path.exists():
            raise HTTPException(
                status_code=404,
                detail="קובץ הדרישות לא נמצא"
            )
        
        content = requirements_path.read_text(encoding="utf-8")
        
        return {
            "success": True,
            "content": content,
            "file_path": str(requirements_path),
            "length": len(content)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get requirements", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"אירעה שגיאה בקריאת הדרישות: {str(e)}"
        )


@router.post("/reload-requirements")
async def reload_requirements():
    """Reload requirements from requirements-mamad.md file.
    
    This endpoint allows refreshing the requirements without restarting the server.
    
    Returns:
        Success message with updated requirements info
    """
    logger.info("Reloading requirements from file")
    
    try:
        # Get fresh validator instance which will reload the file
        from src.services.llm_validator import LLMValidator
        global _llm_validator_instance
        _llm_validator_instance = LLMValidator()
        
        return {
            "success": True,
            "message": "הדרישות נטענו מחדש בהצלחה מקובץ requirements-mamad.md",
            "requirements_length": len(_llm_validator_instance.requirements_content)
        }
        
    except Exception as e:
        logger.error("Failed to reload requirements", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"אירעה שגיאה בטעינת הדרישות: {str(e)}"
        )


@router.delete("/results/{validation_id}")
async def delete_validation_result(validation_id: str):
    """Delete a validation result and associated plan file.
    
    Args:
        validation_id: Validation result to delete
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If validation not found
    """
    logger.info("Deleting validation result", validation_id=validation_id)
    
    try:
        cosmos_client = get_cosmos_client()
        blob_client = get_blob_client()
        
        # First, get the validation result to find blob URL and partition key
        query = "SELECT * FROM c WHERE c.id = @validation_id"
        parameters = [{"name": "@validation_id", "value": validation_id}]
        results = await cosmos_client.query_items(query, parameters)
        
        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"תוצאת בדיקה לא נמצאה: {validation_id}"
            )
        
        result = results[0]
        project_id = result["project_id"]
        plan_blob_url = result.get("plan_blob_url")
        
        # Delete from Cosmos DB
        deleted = await cosmos_client.delete_item(validation_id, project_id)
        
        # Delete blob if exists
        if plan_blob_url:
            try:
                blob_name = plan_blob_url.split("/")[-3:]  # Extract from URL
                blob_name = "/".join(blob_name)
                await blob_client.delete_blob(blob_name)
                logger.info("Deleted plan blob", blob_name=blob_name)
            except Exception as blob_error:
                logger.warning("Failed to delete blob", error=str(blob_error))
        
        logger.info("Validation result deleted", validation_id=validation_id)
        
        return {
            "success": True,
            "message": f"תוצאת בדיקה נמחקה בהצלחה: {validation_id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete validation result", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"אירעה שגיאה במחיקת התוצאה: {str(e)}"
        )
