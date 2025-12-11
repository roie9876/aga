"""File conversion utilities for architectural plans."""
import io
import os
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image

from src.utils.logging import get_logger

logger = get_logger(__name__)


def convert_dwf_to_image(dwf_bytes: bytes, filename: str) -> Tuple[bytes, str]:
    """Convert DWF/DWFX file to PNG using Docker + ODA FileConverter.
    
    Process:
    1. Save DWF to temporary directory
    2. Run ODA FileConverter in Docker container (Linux CLI version)
    3. Convert resulting DWG to PNG using ezdxf + matplotlib
    4. Return PNG bytes
    
    Args:
        dwf_bytes: Raw DWF/DWFX file bytes
        filename: Original filename
        
    Returns:
        Tuple of (image_bytes, new_filename)
        
    Raises:
        ValueError: If Docker is not available or conversion fails
    """
    logger.info("Converting DWF to PNG using Docker + ODA FileConverter", filename=filename)
    
    # Check if Docker is available
    try:
        result = subprocess.run(
            ['docker', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            raise ValueError("Docker is not running")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.error("Docker not available")
        raise ValueError(
            "❌ Docker לא זמין\n\n"
            "המרת DWF דורשת Docker.\n\n"
            "אופציות:\n"
            "1. התקן Docker Desktop: https://www.docker.com/products/docker-desktop\n"
            "2. או המר ידנית:\n"
            "   • פתח ODA File Converter\n"
            "   • המר DWF → DWG\n"
            "   • פתח ב-FreeCAD\n"
            "   • ייצא כ-PNG\n"
            "   • העלה את ה-PNG"
        )
    
    # Check if ODA Docker image exists, build if not
    try:
        result = subprocess.run(
            ['docker', 'images', '-q', 'oda-converter'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if not result.stdout.strip():
            logger.info("Building ODA Docker image (first time only)...")
            build_result = subprocess.run(
                ['docker', 'build', '-t', 'oda-converter', '-f', 'Dockerfile.oda', '.'],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(Path(__file__).parent.parent.parent)
            )
            if build_result.returncode != 0:
                logger.error("Docker image build failed", stderr=build_result.stderr)
                raise ValueError(f"Failed to build Docker image: {build_result.stderr}")
            logger.info("ODA Docker image built successfully")
    except Exception as e:
        logger.error("Docker image check failed", error=str(e))
        raise ValueError(f"Docker setup failed: {str(e)}")
    
    # Import ezdxf for DWG rendering
    try:
        import ezdxf
        from ezdxf.addons.drawing import RenderContext, Frontend
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
        import matplotlib.pyplot as plt
    except ImportError as e:
        logger.error("Missing dependencies for DWG rendering", error=str(e))
        raise ValueError(
            "חסרות ספריות נדרשות:\n"
            "pip install ezdxf matplotlib"
        )
    
    # Create temporary directories
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_dir = temp_path / "input"
        output_dir = temp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        
        # Save DWF file
        dwf_file = input_dir / filename
        dwf_file.write_bytes(dwf_bytes)
        logger.info("DWF saved to temp file", path=str(dwf_file))
        
        try:
            # Step 1: Convert DWF → DWG using Docker + ODA FileConverter
            cmd = [
                'docker', 'run', '--rm',
                '-v', f'{temp_path}:/data',
                'oda-converter',
                '/data/input',      # Input folder
                '/data/output',     # Output folder
                'ACAD2018',         # Output version
                'DWG',              # Output type
                '0',                # Recurse (0 = no)
                '1',                # Audit (1 = yes)
                '*.DWF'             # Filter
            ]
            
            logger.info("Running ODA FileConverter in Docker", cmd=' '.join(cmd))
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                logger.error("ODA conversion failed", stderr=result.stderr, stdout=result.stdout)
                raise ValueError(f"המרת DWF נכשלה: {result.stderr}")
            
            # Find the output DWG file
            dwg_files = list(output_dir.glob("*.dwg"))
            if not dwg_files:
                logger.error("No DWG file created", output_dir=str(output_dir))
                raise ValueError("לא נוצר קובץ DWG מההמרה")
            
            dwg_file = dwg_files[0]
            logger.info("DWF → DWG conversion successful", dwg_file=str(dwg_file))
            
            # Step 2: Convert DWG → PNG using ezdxf + matplotlib
            logger.info("Converting DWG to PNG", dwg_file=str(dwg_file))
            
            doc = ezdxf.readfile(str(dwg_file))
            msp = doc.modelspace()
            
            # Setup rendering
            fig = plt.figure(figsize=(20, 15), dpi=300)
            ax = fig.add_axes([0, 0, 1, 1])
            ctx = RenderContext(doc)
            out = MatplotlibBackend(ax)
            
            # Render drawing
            Frontend(ctx, out).draw_layout(msp, finalize=True)
            
            # Save to PNG bytes
            png_buffer = io.BytesIO()
            fig.savefig(
                png_buffer,
                format='png',
                dpi=300,
                bbox_inches='tight',
                pad_inches=0,
                facecolor='white'
            )
            plt.close(fig)
            
            png_bytes = png_buffer.getvalue()
            new_filename = filename.rsplit('.', 1)[0] + '.png'
            
            logger.info("DWF → PNG conversion complete", 
                       original=filename, 
                       converted=new_filename,
                       size_kb=len(png_bytes) / 1024)
            
            return png_bytes, new_filename
            
        except subprocess.TimeoutExpired:
            logger.error("ODA conversion timed out")
            raise ValueError("המרת DWF לקחה יותר מדי זמן")
        except Exception as e:
            logger.error("DWF conversion failed", error=str(e))
            raise ValueError(f"שגיאה בהמרת DWF: {str(e)}")


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
    
    # PDF - convert to high-res PNG to preserve quality for tiling
    elif file_type == 'pdf':
        logger.info("Converting PDF to PNG (high resolution)", filename=filename)
        image_bytes, new_filename = convert_pdf_to_image(file_bytes, filename)
        return image_bytes, new_filename, True
    
    else:
        raise ValueError(f"Unknown file type: {filename}")


def convert_pdf_to_image(pdf_bytes: bytes, filename: str) -> Tuple[bytes, str]:
    """Convert PDF to high-resolution PNG.
    
    Uses pdf2image (Poppler) to convert PDF to PNG at 300 DPI
    to preserve detail for GPT analysis and tiling.
    
    Args:
        pdf_bytes: Raw PDF file bytes
        filename: Original filename
        
    Returns:
        Tuple of (png_bytes, new_filename)
        
    Raises:
        ValueError: If conversion fails
    """
    try:
        from pdf2image import convert_from_bytes
    except ImportError:
        logger.error("pdf2image not installed")
        raise ValueError(
            "PDF conversion requires pdf2image library.\n"
            "Install: pip install pdf2image\n"
            "macOS also requires: brew install poppler"
        )
    
    logger.info("Converting PDF to PNG", filename=filename, dpi=300)
    
    try:
        # Convert PDF to images at 300 DPI (high quality for architectural plans)
        images = convert_from_bytes(
            pdf_bytes,
            dpi=300,
            fmt='png',
            use_pdftocairo=True  # Better quality than pdftoppm
        )
        
        if not images:
            raise ValueError("PDF conversion produced no images")
        
        # If multi-page PDF, use first page
        if len(images) > 1:
            logger.warning("Multi-page PDF detected, using first page only", 
                          total_pages=len(images))
        
        image = images[0]
        
        # Convert PIL Image to bytes
        png_buffer = io.BytesIO()
        image.save(png_buffer, format='PNG', optimize=True)
        png_bytes = png_buffer.getvalue()
        
        new_filename = filename.rsplit('.', 1)[0] + '.png'
        
        logger.info("PDF → PNG conversion complete",
                   original=filename,
                   converted=new_filename,
                   size_kb=len(png_bytes) / 1024,
                   dimensions=f"{image.width}x{image.height}")
        
        return png_bytes, new_filename
        
    except Exception as e:
        logger.error("PDF conversion failed", error=str(e))
        raise ValueError(f"Failed to convert PDF: {str(e)}")
