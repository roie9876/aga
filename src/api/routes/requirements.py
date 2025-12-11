"""Requirements endpoints - provides structured access to MAMAD requirements."""
from fastapi import APIRouter, HTTPException
from pathlib import Path
from typing import List, Dict, Any
import re

router = APIRouter(prefix="/requirements", tags=["requirements"])


def parse_requirements_markdown() -> Dict[str, Any]:
    """Parse requirements-mamad.md into structured sections.
    
    Returns:
        Dictionary with sections and their requirements
    """
    requirements_path = Path("requirements-mamad.md")
    
    if not requirements_path.exists():
        raise FileNotFoundError("requirements-mamad.md not found")
    
    content = requirements_path.read_text(encoding="utf-8")
    
    sections = []
    current_section = None
    current_subsection = None
    
    lines = content.split('\n')
    
    for line in lines:
        # Main section (## X. Title)
        if line.startswith('## ') and not line.startswith('###'):
            if current_section:
                sections.append(current_section)
            
            title = line.replace('##', '').strip()
            current_section = {
                "title": title,
                "subsections": []
            }
            current_subsection = None
            
        # Subsection (### X.X Title)
        elif line.startswith('### '):
            if current_section:
                title = line.replace('###', '').strip()
                current_subsection = {
                    "title": title,
                    "requirements": []
                }
                current_section["subsections"].append(current_subsection)
        
        # Requirement (starts with -)
        elif line.strip().startswith('-') and current_subsection:
            requirement = line.strip()[1:].strip()
            if requirement and not requirement.startswith('**'):
                current_subsection["requirements"].append(requirement)
    
    # Add last section
    if current_section:
        sections.append(current_section)
    
    return {
        "title": "דרישות לאישור מרחב מוגן דירתי (ממ״ד)",
        "description": "מסמך זה מרכז את כל הדרישות האדריכליות וההנדסיות החיוניות לבדיקת תוכנית ממ״ד",
        "sections": sections
    }


@router.get("")
async def get_requirements():
    """Get all MAMAD requirements in structured format.
    
    Returns:
        Structured requirements with sections and subsections
    """
    try:
        requirements = parse_requirements_markdown()
        return requirements
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Requirements file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing requirements: {str(e)}")


@router.get("/summary")
async def get_requirements_summary():
    """Get a summary of requirements count by section.
    
    Returns:
        Summary statistics
    """
    try:
        requirements = parse_requirements_markdown()
        
        total_requirements = 0
        section_counts = []
        
        for section in requirements["sections"]:
            section_count = 0
            for subsection in section["subsections"]:
                section_count += len(subsection["requirements"])
            
            total_requirements += section_count
            section_counts.append({
                "section": section["title"],
                "count": section_count
            })
        
        return {
            "total_requirements": total_requirements,
            "total_sections": len(requirements["sections"]),
            "section_counts": section_counts
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
