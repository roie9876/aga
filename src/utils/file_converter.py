"""File conversion utilities for architectural plans.

This app accepts only:
- Images: PNG, JPG, JPEG
- Documents: PDF (converted to PNG)

Autodesk/CAD formats (e.g., DWF/DWFX/DWG) are intentionally not supported.
"""
import io
import os
import math
import re
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image

from src.utils.logging import get_logger

logger = get_logger(__name__)


def is_supported_format(filename: str) -> bool:
    """Check if file format is supported.
    
    Supported formats:
    - Images: PNG, JPG, JPEG
    - Documents: PDF
    
    Args:
        filename: Name of the file
        
    Returns:
        True if format is supported
    """
    supported_extensions = {'.png', '.jpg', '.jpeg', '.pdf'}
    ext = Path(filename).suffix.lower()
    return ext in supported_extensions


def get_file_type(filename: str) -> str:
    """Get file type category.
    
    Args:
        filename: Name of the file
        
    Returns:
        File type: 'image', 'pdf', or 'unknown'
    """
    ext = Path(filename).suffix.lower()
    
    if ext in {'.png', '.jpg', '.jpeg'}:
        return 'image'
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
    
    # Pillow raises DecompressionBombWarning/Error when an image is extremely large in pixels.
    # For architectural plans, rendering at 300 DPI can easily exceed that threshold on large pages.
    # We keep a safe pixel budget to avoid conversion failures and uncontrolled memory usage.
    requested_dpi = int(os.getenv("PDF_CONVERSION_DPI", "300"))
    min_dpi = int(os.getenv("PDF_CONVERSION_MIN_DPI", "100"))
    # Default below Pillow's MAX_IMAGE_PIXELS (~89M) to avoid warnings/errors.
    max_pixels = int(os.getenv("PDF_CONVERSION_MAX_PIXELS", str(80_000_000)))

    effective_dpi = requested_dpi

    # Try to estimate a safe DPI from the PDF page size (in points) before rendering.
    try:
        from pdf2image import pdfinfo_from_bytes

        info = pdfinfo_from_bytes(pdf_bytes, userpw=None, poppler_path=None)
        page_size = info.get("Page size")
        # Example: "841.89 x 595.28 pts (A4)" or similar
        if isinstance(page_size, str):
            match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*x\s*([0-9]+(?:\.[0-9]+)?)", page_size)
            if match:
                w_pts = float(match.group(1))
                h_pts = float(match.group(2))
                # pixels = (w_pts/72*dpi)*(h_pts/72*dpi)
                # => dpi <= sqrt(max_pixels * 72^2 / (w_pts*h_pts))
                max_dpi_by_pixels = int(math.floor(math.sqrt(max_pixels * (72.0**2) / (w_pts * h_pts))))
                effective_dpi = max(min_dpi, min(requested_dpi, max_dpi_by_pixels))
                logger.info(
                    "PDF page size estimated; choosing safe DPI",
                    filename=filename,
                    requested_dpi=requested_dpi,
                    effective_dpi=effective_dpi,
                    max_pixels=max_pixels,
                    page_size_pts=f"{w_pts}x{h_pts}",
                )
    except Exception as e:
        logger.warning("Failed to estimate PDF page size; will rely on fallback DPI retry", error=str(e))

    logger.info("Converting PDF to PNG", filename=filename, dpi=effective_dpi)
    
    try:
        def _render(dpi: int):
            return convert_from_bytes(
                pdf_bytes,
                dpi=dpi,
                fmt='png',
                use_pdftocairo=True  # Better quality than pdftoppm
            )

        try:
            images = _render(effective_dpi)
        except Exception as e:
            # Fallback: progressively reduce DPI if we hit Pillow's decompression-bomb guard.
            msg = str(e)
            if "decompression bomb" not in msg.lower():
                raise
            logger.warning(
                "PDF render hit decompression-bomb guard; retrying with lower DPI",
                filename=filename,
                error=msg,
            )
            images = None
            for dpi in [200, 150, 125, 100, 90, 80]:
                if dpi > effective_dpi:
                    continue
                if dpi < min_dpi:
                    break
                try:
                    images = _render(dpi)
                    effective_dpi = dpi
                    logger.info("PDF render succeeded after DPI reduction", filename=filename, dpi=effective_dpi)
                    break
                except Exception as e2:
                    if "decompression bomb" in str(e2).lower():
                        continue
                    raise
            if images is None:
                raise
        
        if not images:
            raise ValueError("PDF conversion produced no images")
        
        # If multi-page PDF, use first page
        if len(images) > 1:
            logger.warning("Multi-page PDF detected, using first page only", 
                          total_pages=len(images))
        
        image = images[0]

        # If it still ends up huge, downscale to a safe pixel budget.
        pixel_count = int(image.width * image.height)
        if pixel_count > max_pixels:
            scale = math.sqrt(max_pixels / float(pixel_count))
            new_w = max(1, int(image.width * scale))
            new_h = max(1, int(image.height * scale))
            logger.warning(
                "Rendered PDF image exceeds pixel budget; downscaling",
                filename=filename,
                original_dimensions=f"{image.width}x{image.height}",
                new_dimensions=f"{new_w}x{new_h}",
                max_pixels=max_pixels,
            )
            image = image.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)
        
        # Convert PIL Image to bytes
        png_buffer = io.BytesIO()
        image.save(png_buffer, format='PNG', optimize=True)
        png_bytes = png_buffer.getvalue()
        
        new_filename = filename.rsplit('.', 1)[0] + '.png'
        
        logger.info("PDF → PNG conversion complete",
                   original=filename,
                   converted=new_filename,
                   size_kb=len(png_bytes) / 1024,
                   dimensions=f"{image.width}x{image.height}",
                   dpi=effective_dpi)
        
        return png_bytes, new_filename
        
    except Exception as e:
        logger.error("PDF conversion failed", error=str(e))
        raise ValueError(f"Failed to convert PDF: {str(e)}")
