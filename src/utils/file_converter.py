"""File conversion utilities for architectural plans."""
import io
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image
import threading
import time

from src.utils.logging import get_logger

logger = get_logger(__name__)


def convert_dwf_to_image(dwf_bytes: bytes, filename: str) -> Tuple[bytes, str]:
    """Convert DWF/DWFX file to PNG image.
    
    DWF (Design Web Format) and DWFX (DWF XML) files need to be converted to images for GPT-5.1 analysis.
    DWFX is the newer XML-based format that replaced DWF.
    
    Args:
        dwf_bytes: Raw DWF/DWFX file bytes
        filename: Original filename
        
    Returns:
        Tuple of (image_bytes, new_filename)
        
    Raises:
        ValueError: If conversion fails
    """
    logger.info("Converting DWF/DWFX to image", filename=filename)
    
    try:
        # Try using aspose-cad with thread-based timeout protection
        try:
            import aspose.cad as cad
            
            # Save DWF to temp file
            with tempfile.NamedTemporaryFile(suffix='.dwf', delete=False) as tmp:
                tmp.write(dwf_bytes)
                tmp_path = tmp.name
            
            try:
                logger.info("Loading DWF file with Aspose.CAD", path=tmp_path)
                logger.warning("Aspose.CAD conversion may hang - using 20 second timeout")
                
                # Use threading for timeout (works better with native libraries)
                result = {'image_bytes': None, 'error': None}
                
                def convert_dwf():
                    """Thread function to convert DWF."""
                    try:
                        # Load DWF
                        logger.info("Aspose.CAD: Loading DWF...")
                        image = cad.Image.load(tmp_path)
                        logger.info("Aspose.CAD: DWF loaded successfully")
                        
                        # Convert to PNG
                        png_path = tmp_path.replace('.dwf', '.png')
                        
                        # Set rasterization options for Aspose.CAD 25.x
                        logger.info("Aspose.CAD: Setting rasterization options")
                        rasterization_options = cad.imageoptions.CadRasterizationOptions()
                        rasterization_options.page_width = float(1920)
                        rasterization_options.page_height = float(1080)
                        
                        png_options = cad.imageoptions.PngOptions()
                        png_options.vector_rasterization_options = rasterization_options
                        
                        # Save as PNG
                        logger.info("Aspose.CAD: Saving as PNG", path=png_path)
                        image.save(png_path, png_options)
                        logger.info("Aspose.CAD: PNG saved successfully")
                        
                        # Read PNG bytes
                        with open(png_path, 'rb') as f:
                            result['image_bytes'] = f.read()
                        
                        # Cleanup PNG
                        Path(png_path).unlink(missing_ok=True)
                        
                    except Exception as e:
                        result['error'] = str(e)
                        logger.error("Aspose.CAD conversion failed in thread", error=str(e))
                
                # Start conversion in thread
                conversion_thread = threading.Thread(target=convert_dwf, daemon=True)
                conversion_thread.start()
                
                # Wait with timeout (20 seconds)
                conversion_thread.join(timeout=20.0)
                
                if conversion_thread.is_alive():
                    # Thread is still running - timeout!
                    logger.error("DWF conversion timed out after 20 seconds - Aspose.CAD appears to be hanging")
                    raise ValueError(
                        "DWF file conversion timed out after 20 seconds. "
                        "Aspose.CAD library appears to hang on this file. "
                        "Please convert your DWF to PNG manually using AutoCAD, DWG TrueView, "
                        "or an online converter (e.g., https://www.zamzar.com/convert/dwf-to-png/)"
                    )
                
                # Check for errors
                if result['error']:
                    raise ValueError(f"DWF conversion failed: {result['error']}")
                
                if not result['image_bytes']:
                    raise ValueError("DWF conversion failed: no image data returned")
                
                # Success!
                new_filename = filename.rsplit('.', 1)[0] + '.png'
                logger.info("DWF converted successfully using aspose-cad", 
                           original=filename, converted=new_filename,
                           size_kb=len(result['image_bytes']) / 1024)
                
                return result['image_bytes'], new_filename
                    
            finally:
                Path(tmp_path).unlink(missing_ok=True)
                
        except ImportError:
            logger.warning("aspose-cad not installed")
            raise ValueError(
                "DWF/DWFX file conversion requires aspose-cad library. "
                "Please convert your DWF/DWFX file to PNG, JPG, or PDF format manually."
            )
            
            raise ValueError(
                "DWF/DWFX file conversion requires aspose-cad library. "
                "Please convert your DWF/DWFX file to PNG, JPG, or PDF format manually."
            )
            
    except Exception as e:
        logger.error("DWF/DWFX conversion failed", error=str(e), filename=filename)
        raise ValueError(f"Failed to convert DWF/DWFX file: {str(e)}")


def is_dwf_file(filename: str) -> bool:
    """Check if file is DWF or DWFX format.
    
    Args:
        filename: Name of the file
        
    Returns:
        True if file is DWF/DWFX
    """
    return filename.lower().endswith(('.dwf', '.dwfx'))


def is_supported_format(filename: str) -> bool:
    """Check if file format is supported.
    
    Supported formats:
    - Images: PNG, JPG, JPEG
    - CAD: DWG (requires conversion), DWF/DWFX (requires conversion)
    - Documents: PDF
    
    Args:
        filename: Name of the file
        
    Returns:
        True if format is supported
    """
    supported_extensions = {'.png', '.jpg', '.jpeg', '.pdf', '.dwg', '.dwf', '.dwfx'}
    ext = Path(filename).suffix.lower()
    return ext in supported_extensions


def get_file_type(filename: str) -> str:
    """Get file type category.
    
    Args:
        filename: Name of the file
        
    Returns:
        File type: 'image', 'cad', 'pdf', or 'unknown'
    """
    ext = Path(filename).suffix.lower()
    
    if ext in {'.png', '.jpg', '.jpeg'}:
        return 'image'
    elif ext in {'.dwg', '.dwf', '.dwfx'}:
        return 'cad'
    elif ext == '.pdf':
        return 'pdf'
    else:
        return 'unknown'


def convert_to_image_if_needed(
    file_bytes: bytes, 
    filename: str
) -> Tuple[bytes, str, bool]:
    """Convert file to image format if needed.
    
    Args:
        file_bytes: Raw file bytes
        filename: Original filename
        
    Returns:
        Tuple of (processed_bytes, processed_filename, was_converted)
        
    Raises:
        ValueError: If file format is not supported or conversion fails
    """
    if not is_supported_format(filename):
        raise ValueError(f"Unsupported file format: {filename}")
    
    file_type = get_file_type(filename)
    
    # Images - no conversion needed
    if file_type == 'image':
        logger.info("File is already an image", filename=filename)
        return file_bytes, filename, False
    
    # DWF/DWFX - needs conversion
    elif filename.lower().endswith(('.dwf', '.dwfx')):
        logger.info("Converting DWF/DWFX file", filename=filename)
        image_bytes, new_filename = convert_dwf_to_image(file_bytes, filename)
        return image_bytes, new_filename, True
    
    # DWG - needs conversion (similar to DWF)
    elif filename.lower().endswith('.dwg'):
        logger.warning("DWG conversion not yet implemented", filename=filename)
        raise ValueError(
            "DWG file format requires conversion. "
            "Please convert to PDF, PNG, or JPG format, or use DWF format."
        )
    
    # PDF - no conversion needed (GPT-5.1 supports PDF)
    elif file_type == 'pdf':
        logger.info("File is PDF - no conversion needed", filename=filename)
        return file_bytes, filename, False
    
    else:
        raise ValueError(f"Unknown file type: {filename}")
