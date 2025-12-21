"""Auto-segmentation pipeline (Option A + OCR) for architectural sheets."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import math
import os
import re
import shutil
import subprocess
import tempfile

from PIL import Image

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    cv2 = None
    np = None


class DependencyError(RuntimeError):
    """Raised when optional CV/OCR dependencies are missing."""


@dataclass
class SegmenterConfig:
    mode: str = "cv"  # cv | layout | detector
    dpi: int = 400
    max_dim: int = 4200
    min_area_ratio: float = 0.005
    max_area_ratio: float = 0.55
    min_width: int = 120
    min_height: int = 120
    min_rectangularity: float = 0.20
    merge_iou_threshold: float = 0.20
    containment_threshold: float = 0.90
    close_kernel: int = 5
    close_iterations: int = 2
    adaptive_block_size: int = 31
    adaptive_c: int = 10
    projection_density_threshold: float = 0.01
    projection_min_gap: int = 25
    split_large_area_ratio: float = 0.18
    split_large_min_boxes: int = 2
    line_kernel_scale: int = 30
    line_merge_iterations: int = 1
    separator_line_density: float = 0.60
    separator_min_line_width: int = 3
    separator_min_gap: int = 40
    separator_min_height_ratio: float = 0.65
    separator_max_width: int = 12
    min_segment_width_ratio: float = 0.04
    hough_threshold: int = 40
    hough_min_line_length_ratio: float = 0.60
    hough_max_line_gap: int = 20
    hough_cluster_px: int = 12
    min_ink_ratio: float = 0.0015
    min_ink_pixels: int = 200
    content_crop_enabled: bool = True
    content_crop_pad: int = 10
    content_density_threshold: float = 0.0025
    content_min_span_ratio: float = 0.15
    edge_refine_enabled: bool = True
    edge_refine_pad: int = 6
    deskew: bool = False
    refine_by_content: bool = True
    refine_pad: int = 6
    ocr_enabled: bool = True
    ocr_lang: str = "heb+eng"
    ocr_psm: int = 6
    ocr_oem: int = 1
    tesseract_cmd: str = "tesseract"
    tessdata_dir: Optional[str] = None
    include_ocr_text: bool = False


HEB_PLAN = "\u05ea\u05db\u05e0\u05d9\u05ea"
HEB_PLAN2 = "\u05ea\u05d5\u05db\u05e0\u05d9\u05ea"
HEB_FLOOR = "\u05e7\u05d5\u05de\u05d4"
HEB_SECTION = "\u05d7\u05d8\u05da"
HEB_ELEV = "\u05d7\u05d6\u05d9\u05ea"
HEB_DETAIL = "\u05e4\u05e8\u05d8"
HEB_TABLE = "\u05d8\u05d1\u05dc\u05d4"
HEB_LEGEND = "\u05de\u05e7\u05e8\u05d0"
HEB_SCALE = "\u05e7\u05e0\u05de"
HEB_SIGNATURE = "\u05d7\u05ea\u05d9\u05de\u05d4"

KEYWORDS: Dict[str, List[str]] = {
    "floor_plan": ["floor plan", "plan", "floor", "basement", HEB_PLAN, HEB_PLAN2, HEB_FLOOR],
    "section": ["section", HEB_SECTION],
    "elevation": ["elevation", "facade", HEB_ELEV],
    "detail": ["detail", HEB_DETAIL],
    "table": ["table", "schedule", "list", HEB_TABLE],
    "legend": ["legend", "symbols", HEB_LEGEND],
    "titleblock": ["project", "architect", "date", "scale", "sheet", HEB_SCALE, HEB_SIGNATURE],
}

SCALE_RE = re.compile(r"\b1\s*[:/]\s*\d{2,4}\b")


def _require_cv() -> None:
    if cv2 is None or np is None:
        raise DependencyError("OpenCV is required (pip install opencv-python).")


def load_image(path: str, dpi: int = 400) -> Image.Image:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        try:
            from pdf2image import convert_from_path
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise DependencyError("pdf2image is required for PDF input.") from exc

        images = convert_from_path(path, dpi=dpi, fmt="png", use_pdftocairo=True)
        if not images:
            raise ValueError("PDF conversion produced no images.")
        return images[0].convert("RGB")

    return Image.open(path).convert("RGB")


def resize_for_detection(image: Image.Image, max_dim: int) -> Tuple[Image.Image, float]:
    if max_dim <= 0:
        return image, 1.0
    width, height = image.size
    scale = min(1.0, float(max_dim) / float(max(width, height)))
    if scale >= 1.0:
        return image, 1.0
    new_w = max(1, int(width * scale))
    new_h = max(1, int(height * scale))
    resized = image.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)
    return resized, scale


def pil_to_bgr(image: Image.Image) -> "np.ndarray":
    _require_cv()
    rgb = np.array(image)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def deskew_image(bgr: "np.ndarray") -> Tuple["np.ndarray", float]:
    _require_cv()
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = cv2.findNonZero(bw)
    if coords is None:
        return bgr, 0.0
    rect = cv2.minAreaRect(coords)
    angle = rect[-1]
    if angle < -45:
        angle = 90 + angle
    if abs(angle) < 0.5:
        return bgr, 0.0
    height, width = bgr.shape[:2]
    center = (width // 2, height // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(bgr, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return rotated, angle


def preprocess_for_contours(bgr: "np.ndarray", config: SegmenterConfig) -> "np.ndarray":
    _require_cv()
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    block = max(3, int(config.adaptive_block_size))
    if block % 2 == 0:
        block += 1
    thresh = cv2.adaptiveThreshold(
        blur,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        block,
        int(config.adaptive_c),
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (config.close_kernel, config.close_kernel))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=config.close_iterations)
    return thresh


def _contours(binary: "np.ndarray") -> List["np.ndarray"]:
    _require_cv()
    cnts = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if len(cnts) == 2:
        return cnts[0]
    return cnts[1]


def _box_area(box: Tuple[float, float, float, float]) -> float:
    return max(0.0, box[2]) * max(0.0, box[3])


def _iou(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    union = _box_area(a) + _box_area(b) - inter
    return inter / union if union > 0 else 0.0


def _containment(inner: Tuple[float, float, float, float], outer: Tuple[float, float, float, float]) -> float:
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer
    ix2, iy2 = ix + iw, iy + ih
    ox2, oy2 = ox + ow, oy + oh
    inter_w = max(0.0, min(ix2, ox2) - max(ix, ox))
    inter_h = max(0.0, min(iy2, oy2) - max(iy, oy))
    inter = inter_w * inter_h
    area = _box_area(inner)
    return inter / area if area > 0 else 0.0


def _union(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    x1, y1 = min(ax1, bx1), min(ay1, by1)
    x2, y2 = max(ax2, bx2), max(ay2, by2)
    return (x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1))


def find_candidate_boxes(binary: "np.ndarray", config: SegmenterConfig) -> List[Tuple[float, float, float, float]]:
    _require_cv()
    height, width = binary.shape[:2]
    image_area = max(1.0, float(width * height))
    min_area = image_area * config.min_area_ratio
    max_area = image_area * config.max_area_ratio

    boxes: List[Tuple[float, float, float, float]] = []
    for contour in _contours(binary):
        x, y, w, h = cv2.boundingRect(contour)
        area = float(w * h)
        if area < min_area or area > max_area:
            continue
        if w < config.min_width or h < config.min_height:
            continue
        contour_area = cv2.contourArea(contour)
        rectangularity = contour_area / area if area > 0 else 0.0
        if rectangularity < config.min_rectangularity:
            continue
        boxes.append((float(x), float(y), float(w), float(h)))

    boxes.sort(key=_box_area, reverse=True)
    return boxes


def merge_overlapping_boxes(
    boxes: List[Tuple[float, float, float, float]],
    iou_threshold: float,
    containment_threshold: float,
) -> List[Tuple[float, float, float, float]]:
    if not boxes:
        return []
    merged: List[Tuple[float, float, float, float]] = []
    for box in boxes:
        merged_into = False
        for idx, existing in enumerate(merged):
            if _iou(box, existing) >= iou_threshold:
                merged[idx] = _union(existing, box)
                merged_into = True
                break
            if _containment(box, existing) >= containment_threshold or _containment(existing, box) >= containment_threshold:
                merged[idx] = _union(existing, box)
                merged_into = True
                break
        if not merged_into:
            merged.append(box)
    return merged


def drop_nested_boxes(
    boxes: List[Tuple[float, float, float, float]], containment_threshold: float
) -> List[Tuple[float, float, float, float]]:
    if not boxes:
        return []
    kept: List[Tuple[float, float, float, float]] = []
    for box in boxes:
        nested = False
        for other in boxes:
            if other == box:
                continue
            if _box_area(other) <= _box_area(box):
                continue
            if _containment(box, other) >= containment_threshold:
                nested = True
                break
        if not nested:
            kept.append(box)
    kept.sort(key=lambda b: (b[1], b[0]))
    return kept


def _projection_splits(
    binary: "np.ndarray",
    axis: int,
    density_threshold: float,
    min_gap: int,
    min_size: int,
) -> List[Tuple[int, int]]:
    _require_cv()
    if axis == 0:
        size = binary.shape[1]
        denom = max(1, binary.shape[0])
        counts = np.count_nonzero(binary, axis=0)
    else:
        size = binary.shape[0]
        denom = max(1, binary.shape[1])
        counts = np.count_nonzero(binary, axis=1)

    density = counts.astype("float32") / float(denom)
    gaps: List[Tuple[int, int]] = []
    in_gap = False
    start = 0
    for i in range(size):
        if density[i] <= density_threshold:
            if not in_gap:
                in_gap = True
                start = i
        else:
            if in_gap:
                end = i
                if end - start >= min_gap:
                    gaps.append((start, end))
                in_gap = False
    if in_gap:
        end = size
        if end - start >= min_gap:
            gaps.append((start, end))

    ranges: List[Tuple[int, int]] = []
    cursor = 0
    for g0, g1 in gaps:
        if g0 - cursor >= min_size:
            ranges.append((cursor, g0))
        cursor = g1
    if size - cursor >= min_size:
        ranges.append((cursor, size))
    return ranges


def _tight_bbox_from_slice(
    binary: "np.ndarray",
    x0: int,
    y0: int,
    x1: int,
    y1: int,
) -> Optional[Tuple[float, float, float, float]]:
    _require_cv()
    if x1 <= x0 or y1 <= y0:
        return None
    sub = binary[y0:y1, x0:x1]
    coords = cv2.findNonZero(sub)
    if coords is None:
        return None
    rx, ry, rw, rh = cv2.boundingRect(coords)
    return (float(x0 + rx), float(y0 + ry), float(rw), float(rh))


def propose_boxes_by_projection(binary: "np.ndarray", config: SegmenterConfig) -> List[Tuple[float, float, float, float]]:
    _require_cv()
    height, width = binary.shape[:2]
    x_ranges = _projection_splits(
        binary,
        axis=0,
        density_threshold=config.projection_density_threshold,
        min_gap=config.projection_min_gap,
        min_size=config.min_width,
    )
    if not x_ranges:
        x_ranges = [(0, width)]

    boxes: List[Tuple[float, float, float, float]] = []
    for x0, x1 in x_ranges:
        sub = binary[:, x0:x1]
        y_ranges = _projection_splits(
            sub,
            axis=1,
            density_threshold=config.projection_density_threshold,
            min_gap=config.projection_min_gap,
            min_size=config.min_height,
        )
        if not y_ranges:
            y_ranges = [(0, height)]
        for y0, y1 in y_ranges:
            tight = _tight_bbox_from_slice(binary, x0, y0, x1, y1)
            if not tight:
                continue
            bx, by, bw, bh = tight
            if bw < config.min_width or bh < config.min_height:
                continue
            boxes.append((bx, by, bw, bh))
    return boxes


def propose_boxes_by_lines(binary: "np.ndarray", config: SegmenterConfig) -> List[Tuple[float, float, float, float]]:
    _require_cv()
    height, width = binary.shape[:2]
    kernel_scale = max(10, int(config.line_kernel_scale))
    h_len = max(12, int(width / kernel_scale))
    v_len = max(12, int(height / kernel_scale))

    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))

    horiz = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel, iterations=1)
    vert = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel, iterations=1)
    lines = cv2.bitwise_or(horiz, vert)
    if config.line_merge_iterations > 0:
        merge_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        lines = cv2.morphologyEx(lines, cv2.MORPH_CLOSE, merge_kernel, iterations=config.line_merge_iterations)

    boxes: List[Tuple[float, float, float, float]] = []
    height, width = lines.shape[:2]
    image_area = max(1.0, float(width * height))
    min_area = image_area * config.min_area_ratio
    max_area = image_area * config.max_area_ratio

    for contour in _contours(lines):
        x, y, w, h = cv2.boundingRect(contour)
        area = float(w * h)
        if area < min_area or area > max_area:
            continue
        if w < config.min_width or h < config.min_height:
            continue
        contour_area = cv2.contourArea(contour)
        rectangularity = contour_area / area if area > 0 else 0.0
        if rectangularity < config.min_rectangularity * 0.6:
            continue
        boxes.append((float(x), float(y), float(w), float(h)))

    boxes.sort(key=_box_area, reverse=True)
    return boxes


def propose_boxes_by_vertical_separators(
    binary: "np.ndarray",
    config: SegmenterConfig,
    content_bbox: Optional[Tuple[int, int, int, int]],
) -> Tuple[List[Tuple[float, float, float, float]], List[int], Dict[str, Any]]:
    _require_cv()
    height, width = binary.shape[:2]
    x0, y0, x1, y1 = 0, 0, width, height
    if content_bbox:
        cx0, cy0, cw, ch = content_bbox
        cx1 = cx0 + cw
        cy1 = cy0 + ch
        cx0 = max(0, min(width, int(cx0)))
        cy0 = max(0, min(height, int(cy0)))
        cx1 = max(0, min(width, int(cx1)))
        cy1 = max(0, min(height, int(cy1)))
        if cx1 > cx0 and cy1 > cy0:
            x0, y0, x1, y1 = cx0, cy0, cx1, cy1

    if x1 <= x0 or y1 <= y0:
        return [], [], {"reason": "empty_band"}

    band = binary[y0:y1, x0:x1]
    band_h = max(1, band.shape[0])
    band_w = max(1, band.shape[1])
    debug: Dict[str, Any] = {
        "band_height": int(band_h),
        "band_width": int(band_w),
        "used_bbox": [int(x0), int(y0), int(x1), int(y1)],
    }

    # Extract long vertical line components, then use column density to find separators.
    v_len = max(12, int(float(band_h) * float(config.separator_min_height_ratio)))
    v_len = min(v_len, band_h)
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))
    vert = cv2.morphologyEx(band, cv2.MORPH_OPEN, v_kernel, iterations=1)
    if config.line_merge_iterations > 0:
        merge_len = max(3, int(v_len * 0.25))
        merge_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, merge_len))
        vert = cv2.morphologyEx(vert, cv2.MORPH_CLOSE, merge_kernel, iterations=config.line_merge_iterations)
    debug["v_len"] = int(v_len)

    col_counts = np.count_nonzero(vert, axis=0).astype("float32")
    col_density = col_counts / float(max(1, band_h))
    max_density = float(col_density.max()) if col_density.size else 0.0
    debug["max_density"] = round(max_density, 4)
    if max_density <= 0.0:
        debug["reason"] = "no_vertical_signal"
        return [], [], debug

    density_threshold = max(0.05, max_density * float(config.separator_line_density))
    debug["density_threshold"] = round(density_threshold, 4)
    candidate_cols = np.where(col_density >= density_threshold)[0]
    max_width = int(config.separator_max_width)
    min_width = int(max(1, config.separator_min_line_width))
    raw_positions: List[int] = []
    if candidate_cols.size:
        start = int(candidate_cols[0])
        prev = start
        for col in candidate_cols[1:]:
            col = int(col)
            if col == prev + 1:
                prev = col
                continue
            run_w = prev - start + 1
            if min_width <= run_w <= max_width:
                raw_positions.append(int((start + prev) / 2))
            start = col
            prev = col
        run_w = prev - start + 1
        if min_width <= run_w <= max_width:
            raw_positions.append(int((start + prev) / 2))
    debug["candidate_cols"] = int(candidate_cols.size)
    debug["raw_positions"] = int(len(raw_positions))

    if not raw_positions:
        min_len = int(float(config.hough_min_line_length_ratio) * float(band_h))
        if min_len > 0:
            edges = cv2.Canny(band, 50, 150)
            edges = cv2.dilate(edges, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=1)
            lines = cv2.HoughLinesP(
                edges,
                rho=1,
                theta=np.pi / 180.0,
                threshold=int(config.hough_threshold),
                minLineLength=max(10, min_len),
                maxLineGap=int(config.hough_max_line_gap),
            )
            if lines is not None:
                for line in lines[:, 0]:
                    x1, y1, x2, y2 = line
                    dx = abs(x2 - x1)
                    dy = abs(y2 - y1)
                    if dx > max(6, max_width):
                        continue
                    if dy < min_len:
                        continue
                    raw_positions.append(int((x1 + x2) / 2))
        debug["hough_positions"] = int(len(raw_positions))

    if not raw_positions:
        debug["reason"] = "no_separators_found"
        return [], [], debug

    raw_positions = sorted(raw_positions)
    cluster_px = max(2, int(config.hough_cluster_px))
    clustered: List[int] = []
    current: List[int] = []
    for pos in raw_positions:
        if not current:
            current = [pos]
            continue
        if abs(pos - current[-1]) <= cluster_px:
            current.append(pos)
        else:
            clustered.append(int(sum(current) / len(current)))
            current = [pos]
    if current:
        clustered.append(int(sum(current) / len(current)))

    min_gap = int(config.separator_min_gap)
    edge_margin = max(10, int(min_gap * 0.5))
    line_positions: List[int] = []
    for pos in clustered:
        if pos < edge_margin or pos > (band_w - edge_margin):
            continue
        if all(abs(pos - k) >= min_gap for k in line_positions):
            line_positions.append(pos)

    if not line_positions:
        debug["reason"] = "filtered_all_separators"
        return [], [], debug
    boxes: List[Tuple[float, float, float, float]] = []
    prev = 0
    for pos in line_positions:
        x_left = x0 + prev
        x_right = x0 + pos
        if x_right - x_left >= config.min_width:
            tight = _tight_bbox_from_slice(binary, x_left, y0, x_right, y1)
            if tight:
                boxes.append(tight)
        prev = pos
    x_left = x0 + prev
    x_right = x1
    if x_right - x_left >= config.min_width:
        tight = _tight_bbox_from_slice(binary, x_left, y0, x_right, y1)
        if tight:
            boxes.append(tight)

    debug["line_positions"] = int(len(line_positions))
    debug["boxes"] = int(len(boxes))
    return boxes, line_positions, debug


def propose_boxes_by_projection_in_region(
    binary: "np.ndarray",
    config: SegmenterConfig,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
) -> List[Tuple[float, float, float, float]]:
    _require_cv()
    if x1 <= x0 or y1 <= y0:
        return []
    sub = binary[y0:y1, x0:x1]
    height, width = sub.shape[:2]
    x_ranges = _projection_splits(
        sub,
        axis=0,
        density_threshold=config.projection_density_threshold,
        min_gap=config.projection_min_gap,
        min_size=config.min_width,
    )
    if not x_ranges:
        x_ranges = [(0, width)]

    boxes: List[Tuple[float, float, float, float]] = []
    for sx0, sx1 in x_ranges:
        sub_x = sub[:, sx0:sx1]
        y_ranges = _projection_splits(
            sub_x,
            axis=1,
            density_threshold=config.projection_density_threshold,
            min_gap=config.projection_min_gap,
            min_size=config.min_height,
        )
        if not y_ranges:
            y_ranges = [(0, height)]
        for sy0, sy1 in y_ranges:
            tight = _tight_bbox_from_slice(sub, sx0, sy0, sx1, sy1)
            if not tight:
                continue
            bx, by, bw, bh = tight
            if bw < config.min_width or bh < config.min_height:
                continue
            boxes.append((float(x0 + bx), float(y0 + by), float(bw), float(bh)))
    return boxes


def split_large_boxes_by_projection(
    binary: "np.ndarray",
    boxes: List[Tuple[float, float, float, float]],
    config: SegmenterConfig,
) -> List[Tuple[float, float, float, float]]:
    if not boxes:
        return []
    height, width = binary.shape[:2]
    image_area = max(1.0, float(width * height))
    output: List[Tuple[float, float, float, float]] = []
    for box in boxes:
        x, y, w, h = box
        area_ratio = _box_area(box) / image_area
        if area_ratio < config.split_large_area_ratio:
            output.append(box)
            continue
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(width, int(x + w))
        y1 = min(height, int(y + h))
        split_boxes = propose_boxes_by_projection_in_region(binary, config, x0, y0, x1, y1)
        if len(split_boxes) >= config.split_large_min_boxes:
            output.extend(split_boxes)
        else:
            output.append(box)
    return output


def merge_narrow_boxes(
    boxes: List[Tuple[float, float, float, float]],
    min_width_ratio: float,
    image_width: int,
) -> List[Tuple[float, float, float, float]]:
    if not boxes or image_width <= 0:
        return boxes
    min_width = max(1.0, float(image_width) * float(min_width_ratio))
    boxes = sorted(boxes, key=lambda b: b[0])
    merged: List[Tuple[float, float, float, float]] = []
    idx = 0
    while idx < len(boxes):
        box = boxes[idx]
        x, y, w, h = box
        if w >= min_width or len(boxes) == 1:
            merged.append(box)
            idx += 1
            continue
        # Merge with the closer neighbor (prefer right if exists)
        if idx + 1 < len(boxes):
            right = boxes[idx + 1]
            merged.append(_union(box, right))
            idx += 2
        else:
            # merge with previous
            prev = merged.pop() if merged else box
            merged.append(_union(prev, box))
            idx += 1
    return merged


def refine_bbox_by_content(
    image: Image.Image,
    bbox: Tuple[float, float, float, float],
    pad: int,
) -> Tuple[float, float, float, float]:
    _require_cv()
    x, y, w, h = bbox
    if w <= 1 or h <= 1:
        return bbox
    crop = image.crop((int(x), int(y), int(x + w), int(y + h)))
    bgr = pil_to_bgr(crop)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = cv2.findNonZero(bw)
    if coords is None:
        return bbox
    rx, ry, rw, rh = cv2.boundingRect(coords)
    nx = max(0, int(x + rx - pad))
    ny = max(0, int(y + ry - pad))
    nx2 = min(image.width, int(x + rx + rw + pad))
    ny2 = min(image.height, int(y + ry + rh + pad))
    return (float(nx), float(ny), float(max(1, nx2 - nx)), float(max(1, ny2 - ny)))


def refine_bbox_by_edges(
    image: Image.Image,
    bbox: Tuple[float, float, float, float],
    pad: int,
) -> Tuple[float, float, float, float]:
    _require_cv()
    x, y, w, h = bbox
    if w <= 1 or h <= 1:
        return bbox
    crop = image.crop((int(x), int(y), int(x + w), int(y + h)))
    bgr = pil_to_bgr(crop)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edges = cv2.dilate(edges, kernel, iterations=1)
    coords = cv2.findNonZero(edges)
    if coords is None:
        return bbox
    rx, ry, rw, rh = cv2.boundingRect(coords)
    nx = max(0, int(x + rx - pad))
    ny = max(0, int(y + ry - pad))
    nx2 = min(image.width, int(x + rx + rw + pad))
    ny2 = min(image.height, int(y + ry + rh + pad))
    return (float(nx), float(ny), float(max(1, nx2 - nx)), float(max(1, ny2 - ny)))


def _line_metrics(bgr: "np.ndarray") -> Dict[str, float]:
    _require_cv()
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    bw = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 21, 10
    )
    height, width = bw.shape[:2]
    area = max(1.0, float(width * height))
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(10, width // 10), 1))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(10, height // 10)))
    horiz = cv2.morphologyEx(bw, cv2.MORPH_OPEN, h_kernel)
    vert = cv2.morphologyEx(bw, cv2.MORPH_OPEN, v_kernel)
    h_density = float(cv2.countNonZero(horiz)) / area
    v_density = float(cv2.countNonZero(vert)) / area
    return {
        "h_density": h_density,
        "v_density": v_density,
        "table_score": min(h_density, v_density),
    }


def _parse_tesseract_tsv(tsv: str) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    lines = [ln for ln in tsv.splitlines() if ln.strip()]
    if not lines:
        return "", [], []
    header = lines[0].split("\t")
    idx = {name: i for i, name in enumerate(header)}
    words: List[Dict[str, Any]] = []
    line_map: Dict[Tuple[int, int, int], Dict[str, Any]] = {}

    for row in lines[1:]:
        parts = row.split("\t")
        if len(parts) != len(header):
            continue
        text = parts[idx.get("text", -1)].strip() if "text" in idx else ""
        if not text:
            continue
        try:
            conf = float(parts[idx["conf"]]) if "conf" in idx else -1.0
        except ValueError:
            conf = -1.0
        if conf < 0:
            continue
        try:
            left = int(parts[idx["left"]])
            top = int(parts[idx["top"]])
            width = int(parts[idx["width"]])
            height = int(parts[idx["height"]])
        except Exception:
            continue
        word = {
            "text": text,
            "bbox": {"x": left, "y": top, "width": width, "height": height},
            "conf": conf,
        }
        words.append(word)
        try:
            block = int(parts[idx["block_num"]])
            par = int(parts[idx["par_num"]])
            line = int(parts[idx["line_num"]])
            line_id = (block, par, line)
        except Exception:
            line_id = (0, 0, 0)
        entry = line_map.setdefault(line_id, {"words": [], "bbox": None, "conf": []})
        entry["words"].append(word)
        entry["conf"].append(conf)
        bx = word["bbox"]
        if entry["bbox"] is None:
            entry["bbox"] = {"x": bx["x"], "y": bx["y"], "width": bx["width"], "height": bx["height"]}
        else:
            ex = entry["bbox"]
            x1 = min(ex["x"], bx["x"])
            y1 = min(ex["y"], bx["y"])
            x2 = max(ex["x"] + ex["width"], bx["x"] + bx["width"])
            y2 = max(ex["y"] + ex["height"], bx["y"] + bx["height"])
            entry["bbox"] = {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}

    line_items: List[Dict[str, Any]] = []
    for entry in line_map.values():
        text = " ".join(w["text"] for w in entry["words"]).strip()
        if not text:
            continue
        avg_conf = sum(entry["conf"]) / len(entry["conf"]) if entry["conf"] else 0.0
        line_items.append({"text": text, "bbox": entry["bbox"], "conf": avg_conf})

    line_items.sort(key=lambda l: (l["bbox"]["y"], l["bbox"]["x"]))
    full_text = "\n".join(item["text"] for item in line_items)
    return full_text, words, line_items


def run_tesseract_ocr(
    image: Image.Image,
    lang: str,
    psm: int,
    oem: int,
    cmd: str,
    tessdata_dir: Optional[str],
) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    if shutil.which(cmd) is None:
        return "", [], []

    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        image.save(tmp.name, format="PNG")
        env = os.environ.copy()
        if tessdata_dir:
            env["TESSDATA_PREFIX"] = tessdata_dir
        tsv_cmd = [
            cmd,
            tmp.name,
            "stdout",
            "-l",
            lang,
            "--oem",
            str(oem),
            "--psm",
            str(psm),
            "tsv",
        ]
        try:
            result = subprocess.run(
                tsv_cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
        except Exception:
            return "", [], []
        return _parse_tesseract_tsv(result.stdout)


def _keyword_hits(text: str, keywords: List[str]) -> List[str]:
    hits = []
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower or kw in text:
            hits.append(kw)
    return hits


def _pick_label_line(lines: List[Dict[str, Any]], keywords: List[str]) -> Tuple[str, Optional[Dict[str, int]]]:
    best_text = ""
    best_bbox = None
    best_score = -1.0
    for item in lines:
        line = item.get("text", "")
        if not line:
            continue
        score = 0.0
        hits = _keyword_hits(line, keywords)
        score += float(len(hits)) * 2.0
        if SCALE_RE.search(line):
            score += 1.5
        score += min(1.0, len(line) / 40.0)
        if score > best_score:
            best_score = score
            best_text = line
            best_bbox = item.get("bbox")
    return best_text, best_bbox


def classify_region(
    ocr_text: str,
    ocr_lines: List[Dict[str, Any]],
    line_metrics: Dict[str, float],
    bbox: Tuple[float, float, float, float],
    page_size: Tuple[int, int],
) -> Dict[str, Any]:
    text = ocr_text or ""
    x, y, w, h = bbox
    page_w, page_h = page_size
    area = max(1.0, float(w * h))
    char_count = len(re.sub(r"\s+", "", text))
    text_density = (char_count / area) * 10000.0

    keyword_hits: Dict[str, List[str]] = {
        key: _keyword_hits(text, terms) for key, terms in KEYWORDS.items()
    }
    table_score = float(line_metrics.get("table_score", 0.0))

    bottom_zone = (y + h) > (page_h * 0.72)
    right_zone = (x + w) > (page_w * 0.60)
    wide_short = (w / max(1.0, h)) >= 3.5 and h < (page_h * 0.25)

    category = "drawing"
    region_type = "unknown"
    confidence = 0.35

    if table_score > 0.015 or keyword_hits["table"]:
        category = "table"
        region_type = "table"
        confidence = 0.75 + min(0.15, table_score * 3.0)
        if keyword_hits["table"]:
            confidence += 0.10
    elif keyword_hits["legend"]:
        category = "drawing"
        region_type = "legend"
        confidence = 0.70
    elif keyword_hits["floor_plan"]:
        category = "drawing"
        region_type = "floor_plan"
        confidence = 0.72
    elif keyword_hits["section"]:
        category = "drawing"
        region_type = "section"
        confidence = 0.70
    elif keyword_hits["elevation"]:
        category = "drawing"
        region_type = "elevation"
        confidence = 0.70
    elif keyword_hits["detail"]:
        category = "drawing"
        region_type = "detail"
        confidence = 0.68
    elif keyword_hits["titleblock"] or (text_density > 1.2 and (bottom_zone or wide_short or right_zone)):
        category = "titleblock"
        region_type = "titleblock"
        confidence = 0.65
    elif text_density > 1.0:
        category = "text"
        region_type = "text"
        confidence = 0.55

    if SCALE_RE.search(text):
        confidence += 0.05
    confidence = max(0.15, min(0.95, confidence))

    label_keywords = KEYWORDS.get(region_type, []) + KEYWORDS.get("titleblock", [])
    label_text, label_bbox = _pick_label_line(ocr_lines, label_keywords)

    return {
        "category": category,
        "type": region_type,
        "confidence": confidence,
        "label_text": label_text,
        "label_bbox": label_bbox,
        "text_density": text_density,
        "table_score": table_score,
    }


def propose_regions_layout_model(*_args: Any, **_kwargs: Any) -> List[Tuple[float, float, float, float]]:
    raise NotImplementedError("Layout model mode is not wired yet.")


def propose_regions_custom_detector(*_args: Any, **_kwargs: Any) -> List[Tuple[float, float, float, float]]:
    raise NotImplementedError("Custom detector mode is not wired yet.")


def segment_image(image: Image.Image, config: SegmenterConfig) -> Dict[str, Any]:
    _require_cv()
    if config.mode not in {"cv", "layout", "detector"}:
        raise ValueError(f"Unknown mode: {config.mode}")

    detect_image, scale = resize_for_detection(image, config.max_dim)
    bgr = pil_to_bgr(detect_image)
    if config.deskew:
        bgr, _ = deskew_image(bgr)
    binary = preprocess_for_contours(bgr, config)
    offset_x = 0
    offset_y = 0
    content_bbox = None
    if config.content_crop_enabled:
        def _dense_bounds(axis: int) -> Optional[Tuple[int, int]]:
            if axis == 0:
                counts = np.count_nonzero(binary, axis=0)
                denom = max(1, binary.shape[0])
                size = binary.shape[1]
            else:
                counts = np.count_nonzero(binary, axis=1)
                denom = max(1, binary.shape[1])
                size = binary.shape[0]
            density = counts.astype("float32") / float(denom)
            thresh = float(config.content_density_threshold)
            idx = np.where(density >= thresh)[0]
            if idx.size == 0:
                return None
            start = int(idx[0])
            end = int(idx[-1]) + 1
            min_span = int(size * float(config.content_min_span_ratio))
            if end - start < min_span:
                return None
            return start, end

        row_bounds = _dense_bounds(axis=1)
        col_bounds = _dense_bounds(axis=0)
        if row_bounds and col_bounds:
            y0, y1 = row_bounds
            x0, x1 = col_bounds
        else:
            coords = cv2.findNonZero(binary)
            if coords is None:
                x0 = y0 = 0
                x1 = binary.shape[1]
                y1 = binary.shape[0]
            else:
                x, y, w, h = cv2.boundingRect(coords)
                x0, y0, x1, y1 = x, y, x + w, y + h

        pad = max(0, int(config.content_crop_pad))
        x0 = max(0, x0 - pad)
        y0 = max(0, y0 - pad)
        x1 = min(binary.shape[1], x1 + pad)
        y1 = min(binary.shape[0], y1 + pad)
        content_bbox = (x0, y0, x1 - x0, y1 - y0)
        area_ratio = (content_bbox[2] * content_bbox[3]) / float(binary.shape[0] * binary.shape[1])
        if area_ratio < 0.95:
            offset_x = x0
            offset_y = y0
            bgr = bgr[y0:y1, x0:x1]
            binary = binary[y0:y1, x0:x1]
    debug: Dict[str, Any] = {
        "initial_boxes": 0,
        "merged_boxes": 0,
        "line_boxes": 0,
        "separator_boxes": 0,
        "separator_lines": 0,
        "projection_boxes": 0,
        "split_boxes": 0,
        "ink_filtered": 0,
        "final_boxes": 0,
        "line_used": False,
        "separator_used": False,
        "projection_used": False,
        "split_used": False,
        "content_bbox": content_bbox,
        "content_offset": {"x": offset_x, "y": offset_y},
    }

    if config.mode == "cv":
        boxes = find_candidate_boxes(binary, config)
    elif config.mode == "layout":
        boxes = propose_regions_layout_model(bgr, config)
    else:
        boxes = propose_regions_custom_detector(bgr, config)

    debug["initial_boxes"] = len(boxes)

    if config.mode == "cv":
        line_boxes = propose_boxes_by_lines(binary, config)
        debug["line_boxes"] = len(line_boxes)
        if len(line_boxes) > len(boxes):
            boxes = line_boxes
            debug["line_used"] = True

        separator_boxes, separator_lines, separator_debug = propose_boxes_by_vertical_separators(
            binary,
            config,
            content_bbox,
        )
        debug["separator_boxes"] = len(separator_boxes)
        debug["separator_lines"] = len(separator_lines)
        debug["separator_debug"] = separator_debug
        if len(separator_boxes) > len(boxes):
            boxes = separator_boxes
            debug["separator_used"] = True

    boxes = merge_overlapping_boxes(boxes, config.merge_iou_threshold, config.containment_threshold)
    boxes = drop_nested_boxes(boxes, config.containment_threshold)
    debug["merged_boxes"] = len(boxes)

    if config.mode == "cv" and len(boxes) <= 1:
        projection_boxes = propose_boxes_by_projection(binary, config)
        debug["projection_boxes"] = len(projection_boxes)
        if len(projection_boxes) > len(boxes):
            boxes = projection_boxes
            debug["projection_used"] = True
            boxes = merge_overlapping_boxes(boxes, config.merge_iou_threshold, config.containment_threshold)
            boxes = drop_nested_boxes(boxes, config.containment_threshold)
    elif config.mode == "cv" and boxes:
        split_boxes = split_large_boxes_by_projection(binary, boxes, config)
        debug["split_boxes"] = len(split_boxes)
        if len(split_boxes) > len(boxes):
            boxes = split_boxes
            debug["split_used"] = True
            boxes = merge_overlapping_boxes(boxes, config.merge_iou_threshold, config.containment_threshold)
            boxes = drop_nested_boxes(boxes, config.containment_threshold)
    if boxes:
        filtered: List[Tuple[float, float, float, float]] = []
        for box in boxes:
            x, y, w, h = box
            x0 = max(0, int(x))
            y0 = max(0, int(y))
            x1 = min(binary.shape[1], int(x + w))
            y1 = min(binary.shape[0], int(y + h))
            if x1 <= x0 or y1 <= y0:
                continue
            roi = binary[y0:y1, x0:x1]
            ink = int(np.count_nonzero(roi))
            area = max(1, int((x1 - x0) * (y1 - y0)))
            ratio = float(ink) / float(area)
            if ink < config.min_ink_pixels or ratio < config.min_ink_ratio:
                debug["ink_filtered"] += 1
                continue
            filtered.append(box)
        boxes = filtered
    debug["final_boxes"] = len(boxes)

    if offset_x or offset_y:
        boxes = [(x + offset_x, y + offset_y, w, h) for (x, y, w, h) in boxes]

    if boxes:
        boxes = merge_narrow_boxes(boxes, config.min_segment_width_ratio, image.width)

    if scale != 1.0:
        boxes = [(x / scale, y / scale, w / scale, h / scale) for (x, y, w, h) in boxes]

    regions: List[Dict[str, Any]] = []
    for idx, box in enumerate(boxes, start=1):
        x, y, w, h = box
        x = max(0.0, min(float(image.width - 1), x))
        y = max(0.0, min(float(image.height - 1), y))
        w = max(1.0, min(float(image.width) - x, w))
        h = max(1.0, min(float(image.height) - y, h))
        refined_box = (x, y, w, h)
        if config.refine_by_content:
            refined_box = refine_bbox_by_content(image, refined_box, config.refine_pad)
        if config.edge_refine_enabled:
            refined_box = refine_bbox_by_edges(image, refined_box, config.edge_refine_pad)
        rx, ry, rw, rh = refined_box
        crop = image.crop((int(rx), int(ry), int(rx + rw), int(ry + rh)))
        bgr_crop = pil_to_bgr(crop)
        line_metrics = _line_metrics(bgr_crop)

        ocr_text = ""
        ocr_words: List[Dict[str, Any]] = []
        ocr_lines: List[Dict[str, Any]] = []
        if config.ocr_enabled:
            ocr_text, ocr_words, ocr_lines = run_tesseract_ocr(
                crop,
                lang=config.ocr_lang,
                psm=config.ocr_psm,
                oem=config.ocr_oem,
                cmd=config.tesseract_cmd,
                tessdata_dir=config.tessdata_dir,
            )

        classification = classify_region(
            ocr_text=ocr_text,
            ocr_lines=ocr_lines,
            line_metrics=line_metrics,
            bbox=refined_box,
            page_size=(image.width, image.height),
        )

        label_bbox = classification.get("label_bbox")
        if label_bbox:
            label_bbox = {
                "x": int(label_bbox["x"] + rx),
                "y": int(label_bbox["y"] + ry),
                "width": int(label_bbox["width"]),
                "height": int(label_bbox["height"]),
            }

        region: Dict[str, Any] = {
            "id": f"R{idx:03d}",
            "x": int(rx),
            "y": int(ry),
            "width": int(rw),
            "height": int(rh),
            "category": classification["category"],
            "type": classification["type"],
            "confidence": round(float(classification["confidence"]), 4),
            "label_text": classification.get("label_text") or "",
            "label_bbox": label_bbox,
        }
        if config.include_ocr_text:
            region["ocr_text"] = ocr_text
            region["ocr_words"] = ocr_words
        regions.append(region)

    return {
        "image_width": int(image.width),
        "image_height": int(image.height),
        "regions": regions,
        "meta": {
            "mode": config.mode,
            "scale": scale,
            "ocr_enabled": bool(config.ocr_enabled),
            "region_count": len(regions),
            "debug": debug,
        },
    }
