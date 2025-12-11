# PDF Support Documentation

## Overview

The application now **fully supports PDF files** for ממ"ד (shelter) plan validation. PDFs are automatically converted to high-resolution PNG images before processing.

## Why Convert PDF → PNG?

1. **Preserve Resolution**: 300 DPI conversion maintains architectural detail
2. **Enable Tiling**: GPT-5.1 can analyze large plans by processing tiles
3. **Uniform Processing**: All formats (DWF, PDF, PNG) go through same pipeline
4. **No Quality Loss**: High-DPI conversion preserves CAD drawing precision

## How It Works

### Pipeline: PDF → PNG → Tiles → GPT Analysis

```
User uploads PDF
    ↓
Backend receives PDF bytes
    ↓
pdf2image converts PDF → PNG at 300 DPI
    ↓
Large PNG can be tiled for processing
    ↓
GPT-5.1 analyzes PNG (full or tiles)
    ↓
Segments identified and cropped
    ↓
Validation rules applied
```

### Technical Details

**Library**: `pdf2image` (Python wrapper for Poppler)
**DPI**: 300 (high quality for architectural plans)
**Format**: PNG with optimization
**Engine**: `pdftocairo` (better quality than pdftoppm)

**Example Conversion:**
- Input: `shelter_plan.pdf` (2MB, vector graphics)
- Output: `shelter_plan.png` (8MB, 3300x4200 pixels at 300 DPI)
- Quality: Preserves all line work, dimensions, and annotations

## Installation Requirements

### Python Package
```bash
pip install pdf2image==1.17.0
```

### System Dependency (Poppler)

**macOS:**
```bash
brew install poppler
```

**Ubuntu/Debian:**
```bash
sudo apt-get install poppler-utils
```

**Windows:**
Download from: http://blog.alivate.com.au/poppler-windows/

## Usage

### Via Web UI

1. Go to http://localhost:5173
2. Click "העלאת תוכנית אדריכלית"
3. Select or drag PDF file
4. System automatically:
   - Converts PDF → PNG (300 DPI)
   - Analyzes with GPT-5.1
   - Segments plan into sections
   - Shows preview for approval

### Supported PDF Types

✅ **Vector PDFs** (best quality):
- Exported from AutoCAD
- Exported from Revit
- Created by architectural software
- CAD drawings saved as PDF

✅ **Raster PDFs** (scanned plans):
- Scanned architectural drawings
- Photos of plans saved as PDF
- Image-based PDFs

⚠️ **Multi-page PDFs**:
- Only **first page** is used
- Warning logged if multiple pages detected

## Code Example

```python
from src.utils.file_converter import convert_pdf_to_image

# Convert PDF to PNG
with open('shelter_plan.pdf', 'rb') as f:
    pdf_bytes = f.read()

png_bytes, new_filename = convert_pdf_to_image(pdf_bytes, 'shelter_plan.pdf')

# Result: png_bytes contains high-res PNG data
# new_filename = 'shelter_plan.png'
```

## Resolution Comparison

| Format | Input Resolution | Output Resolution | Notes |
|--------|-----------------|-------------------|-------|
| DWF | Variable (vector) | 300 DPI PNG | Via ODA + ezdxf |
| PDF | Variable (vector) | 300 DPI PNG | Via pdf2image |
| PNG | As uploaded | Unchanged | Direct use |
| JPG | As uploaded | Unchanged | Direct use |

## Advantages Over Native PDF

### Before (Native PDF to GPT):
- ❌ Cannot tile large PDFs easily
- ❌ Vector data not always interpreted correctly
- ❌ GPT may miss fine details in complex drawings
- ❌ No standard cropping for segments

### After (PDF → PNG → GPT):
- ✅ Consistent raster format for tiling
- ✅ High DPI preserves all details
- ✅ Standard image cropping for segments
- ✅ Same pipeline as DWF/PNG uploads
- ✅ Reliable GPT-5.1 vision analysis

## Performance

**Conversion Time** (typical architectural plan):
- 1-page PDF (A1 size): ~2-3 seconds
- Multi-page PDF: ~2-3 seconds (uses first page only)

**File Sizes:**
- Input PDF: 1-5 MB (vector)
- Output PNG: 5-15 MB (300 DPI raster)

## Troubleshooting

### "pdf2image not installed"
```bash
pip install pdf2image
```

### "poppler not found"
```bash
# macOS
brew install poppler

# Linux
sudo apt-get install poppler-utils
```

### "PDF conversion produced no images"
- Check if PDF is valid (try opening in Preview/Adobe Reader)
- Ensure PDF contains actual content (not blank)
- Verify file is not corrupted

### "Multi-page PDF detected"
This is a warning, not an error. Only the first page is used. If you need a different page:
1. Extract specific page from PDF
2. Upload that page separately

## Future Enhancements

- [ ] Support selecting specific page from multi-page PDF
- [ ] Batch processing of multi-page PDFs
- [ ] OCR for text extraction from raster PDFs
- [ ] Smart page detection (find page with floor plan)

## Summary

**PDF support is fully functional** with high-quality conversion to PNG. Users can now upload shelter plans in PDF format directly, and the system will:

1. Convert to 300 DPI PNG
2. Preserve all architectural details
3. Enable tiling for large plans
4. Process through GPT-5.1 for segmentation
5. Apply ממ"ד validation rules

**Recommended workflow**: Export CAD drawings as PDF (vector format) for best quality.
