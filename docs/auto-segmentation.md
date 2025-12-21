# Auto Segmentation (Option A + OCR)

This doc describes a baseline automatic segmentation pipeline, extension points for model-based layout analysis, and evaluation guidance.

## Proposed Architecture

### Modules
- `rendering/`: PDF or raster input -> high-DPI RGB image
- `preprocess/`: grayscale, denoise, adaptive threshold, optional deskew
- `proposal/`: connected components + contour-based region proposals
- `refine/`: shrink-to-content, snap-to-borders, and de-dup/merge
- `ocr/`: text extraction and label candidates
- `classification/`: region category + type inference
- `export/`: JSON output + crops/thumbnails + overlay

### Data Structures (suggested)
- `RegionProposal`:
  - `id`, `bbox` (x,y,w,h), `score`, `source` (cv/layout/detector)
- `RegionLabel`:
  - `label_text`, `label_bbox`, `keyword_hits`
- `Segment`:
  - `segment_id`, `category` (drawing/table/titleblock/text), `type` (plan/section/detail/legend/unknown)
  - `bbox`, `confidence`, `label_text`, `label_bbox`, `ocr_text` (optional)
- `SegmentationResult`:
  - `image_width`, `image_height`, `regions[]`, `meta` (mode, dpi, scale)

## Baseline Pipeline (Option A + OCR)

1) Render PDF to image at high DPI (300-600).
2) Preprocess:
   - grayscale + blur
   - adaptive threshold (invert)
   - morphological close to connect frame lines
   - optional deskew
3) Proposal:
   - find external contours
   - filter by area, aspect, and rectangularity
   - merge overlaps, drop nested boxes
4) Refinement:
   - shrink to content using thresholded pixels
5) OCR:
   - run Tesseract on each crop
   - detect keywords and scale patterns (e.g. `1:100`)
6) Classification:
   - `table` if strong horizontal+vertical line density
   - `drawing` + specific type if keywords found
   - `titleblock` / `text` if text density + location heuristics
7) Export:
   - JSON with region list
   - optional crops and overlay

## Extension Points

### Option C: Layout Models
Swap the proposal stage with a document layout model (e.g., LayoutParser/Detectron2).
The `mode="layout"` stub in `src/segmentation/auto_segmenter.py` is the integration point:
- Return a list of bounding boxes in the same format.
- Keep the downstream refinement + OCR + classification the same.

### Option D: Custom Detector
Train a detector (YOLOv8/Detectron2) for `drawing/table/titleblock`.
The `mode="detector"` stub in `src/segmentation/auto_segmenter.py` is the integration point:
- Return bounding boxes and optional class scores.
- Use the existing refinement + OCR for label hints and routing.

## Quick Start (PoC)

Dependencies:
- `opencv-python`
- `pdf2image` (already in `requirements.txt` for PDF input)
- Tesseract binary (for OCR) + language data

Run:
```bash
python scripts/auto_segment_poc.py /path/to/plan.pdf \
  --save-overlay \
  --save-crops
```

Outputs:
- `tmp/auto_segments/segments.json`
- `tmp/auto_segments/overlay.png` (if `--save-overlay`)
- `tmp/auto_segments/crops/*.png` (if `--save-crops`)

## Evaluation Metrics

### Region Detection
- **Precision/Recall**: match predicted vs GT boxes at IoU >= 0.5.
- **Over-splitting**: 1 GT matched by multiple predictions (fragmentation rate).
- **Under-splitting**: 1 prediction matches multiple GT boxes (merge rate).

### Crop Tightness
- **IoU with tight GT**: higher is better.
- **Boundary error**: mean absolute edge distance normalized by GT size.

### Type Classification
- **Accuracy/F1** for `drawing/table/titleblock` and sub-types.
- **Confusion matrix** to identify common mix-ups.

### OCR / Labeling
- **Keyword hit rate**: percent of regions where label text contains expected keywords.
- **String similarity** for labels (optional).

### Performance
- Runtime per page and per region
- Memory footprint at target DPI
