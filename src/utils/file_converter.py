"""File conversion utilities for architectural plans.

This app accepts:
- Images: PNG, JPG, JPEG
- Documents: PDF (converted to PNG)
- CAD: DWF/DWFX (converted to PNG via Aspose.CAD if available)
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
    supported_extensions = {'.png', '.jpg', '.jpeg', '.pdf', '.dwf', '.dwfx'}
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
    elif ext in {'.dwf', '.dwfx'}:
        return 'dwf'
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
    
    # DWF/DWFX - convert to high-res PNG via Aspose.CAD
    elif file_type == 'dwf':
        logger.info("Converting DWF/DWFX to PNG (high resolution)", filename=filename)
        image_bytes, new_filename = convert_dwf_to_image(file_bytes, filename)
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
        
        logger.info(
            "PDF → PNG conversion complete",
            original=filename,
            converted=new_filename,
            size_kb=len(png_bytes) / 1024,
            dimensions=f"{image.width}x{image.height}",
            dpi=effective_dpi,
        )

        return png_bytes, new_filename
    except Exception as e:
        logger.error("PDF conversion failed", filename=filename, error=str(e))
        raise ValueError(f"PDF conversion failed: {str(e)}")


def convert_dwf_to_image(dwf_bytes: bytes, filename: str) -> Tuple[bytes, str]:
    """Convert DWF/DWFX to high-resolution PNG using Aspose.CAD.

    Requires: `aspose-cad` Python package.
    """
    try:
        import aspose.cad as cad  # type: ignore
        from aspose.cad.imageoptions import PngOptions, CadRasterizationOptions  # type: ignore
    except Exception as e:
        logger.error("Aspose.CAD not installed", error=str(e))
        raise ValueError(
            "DWF/DWFX conversion requires Aspose.CAD.\n"
            "Install: pip install aspose-cad"
        )

    dpi = int(os.getenv("DWF_CONVERSION_DPI", "600"))

    image = cad.Image.load(io.BytesIO(dwf_bytes))
    raster = CadRasterizationOptions()

    try:
        layouts = []
        if hasattr(image, "layouts") and image.layouts:
            layouts = list(image.layouts)
        elif hasattr(image, "get_layouts"):
            layouts = list(image.get_layouts())  # type: ignore[attr-defined]
        if layouts:
            requested_layout = os.getenv("DWF_CONVERSION_LAYOUT", "").strip()
            render_all = os.getenv("DWF_CONVERSION_RENDER_ALL_LAYOUTS", "0").lower() in {"1", "true", "yes"}
            if requested_layout and requested_layout in layouts:
                raster.layouts = [requested_layout]
                logger.info(
                    "DWF rendering single requested layout",
                    filename=filename,
                    layout=requested_layout,
                )
            elif render_all:
                raster.layouts = layouts
                logger.info(
                    "DWF rendering all layouts",
                    filename=filename,
                    layout_count=len(layouts),
                )
            else:
                raster.layouts = [layouts[0]]
                logger.info(
                    "DWF rendering first layout only",
                    filename=filename,
                    layout=layouts[0],
                    layout_count=len(layouts),
                )
    except Exception:
        pass

    if hasattr(raster, "unit_type"):
        try:
            raster.unit_type = cad.UnitType.PIXEL  # type: ignore[attr-defined]
        except Exception:
            pass
    page_width = float(getattr(image, "width", 5000) or 5000)
    page_height = float(getattr(image, "height", 3500) or 3500)
    override_w = os.getenv("DWF_CONVERSION_PAGE_WIDTH", "").strip()
    override_h = os.getenv("DWF_CONVERSION_PAGE_HEIGHT", "").strip()
    if override_w and override_h:
        try:
            page_width = float(override_w)
            page_height = float(override_h)
        except Exception:
            pass
    scale = float(os.getenv("DWF_CONVERSION_SCALE", "4.0"))
    if scale > 1.0:
        page_width *= scale
        page_height *= scale

    logger.info(
        "DWF raster target size",
        filename=filename,
        page_width=page_width,
        page_height=page_height,
        scale=scale,
    )
    max_pixels = int(os.getenv("DWF_CONVERSION_MAX_PIXELS", str(40_000_000)))
    pixel_count = page_width * page_height
    if pixel_count > max_pixels and page_width > 0 and page_height > 0:
        scale = math.sqrt(max_pixels / pixel_count)
        page_width = max(1.0, page_width * scale)
        page_height = max(1.0, page_height * scale)
        logger.warning(
            "DWF raster size exceeds pixel budget; downscaling",
            filename=filename,
            original_pixels=int(pixel_count),
            max_pixels=max_pixels,
            page_width=page_width,
            page_height=page_height,
        )

    raster.page_width = page_width
    raster.page_height = page_height
    if hasattr(raster, "horizontal_resolution"):
        try:
            raster.horizontal_resolution = float(dpi)
        except Exception:
            pass
    if hasattr(raster, "vertical_resolution"):
        try:
            raster.vertical_resolution = float(dpi)
        except Exception:
            pass

    options = PngOptions()
    options.vector_rasterization_options = raster
    try:
        color_enum = options.color_type.__class__
        options.color_type = color_enum.TRUECOLOR  # type: ignore[attr-defined]
    except Exception:
        pass

    if hasattr(raster, "draw_type"):
        try:
            draw_enum = raster.draw_type.__class__
            raster.draw_type = draw_enum.USE_OBJECT_COLOR  # type: ignore[attr-defined]
        except Exception:
            pass

    if hasattr(raster, "background_color"):
        try:
            raster.background_color = cad.Color.from_argb(255, 255, 255, 255)
        except Exception:
            pass

    if hasattr(raster, "automatic_layouts_scaling"):
        try:
            raster.automatic_layouts_scaling = False
        except Exception:
            pass
    if hasattr(raster, "scale_method"):
        try:
            scale_enum = raster.scale_method.__class__
            raster.scale_method = scale_enum.NONE  # type: ignore[attr-defined]
        except Exception:
            pass
    if hasattr(raster, "relative_scale"):
        try:
            raster.relative_scale = float(os.getenv("DWF_CONVERSION_RELATIVE_SCALE", "1.0"))
        except Exception:
            pass
    if hasattr(raster, "line_scale"):
        try:
            raster.line_scale = float(os.getenv("DWF_CONVERSION_LINE_SCALE", "1.2"))
        except Exception:
            pass

    if hasattr(raster, "quality"):
        try:
            q = raster.quality
            quality_enum = q.text.__class__
            q.text = quality_enum.HIGH
            q.arc = quality_enum.HIGH
            q.hatch = quality_enum.HIGH
            q.objects_precision = quality_enum.HIGH
            if hasattr(q, "text_thickness_normalization"):
                q.text_thickness_normalization = True
            raster.quality = q
        except Exception:
            pass

    out = io.BytesIO()
    image.save(out, options)
    png_bytes = out.getvalue()
    new_filename = f"{Path(filename).stem}.png"
    return png_bytes, new_filename
