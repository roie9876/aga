#!/usr/bin/env python3
"""Run the Option A + OCR auto-segmentation pipeline on a single page."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Tuple

from PIL import Image, ImageDraw

from src.segmentation.auto_segmenter import (
    DependencyError,
    SegmenterConfig,
    load_image,
    segment_image,
)


COLOR_BY_CATEGORY: Dict[str, Tuple[int, int, int]] = {
    "drawing": (0, 120, 255),
    "table": (0, 160, 60),
    "titleblock": (180, 80, 40),
    "text": (160, 80, 180),
    "legend": (120, 120, 120),
}


def save_overlay(image: Image.Image, regions: list[dict], out_path: Path) -> None:
    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)
    for region in regions:
        x = int(region["x"])
        y = int(region["y"])
        w = int(region["width"])
        h = int(region["height"])
        category = str(region.get("category") or "drawing")
        color = COLOR_BY_CATEGORY.get(category, (255, 0, 0))
        draw.rectangle([x, y, x + w, y + h], outline=color, width=3)
        label = f"{region['id']}:{region.get('type', 'unknown')}"
        draw.text((x + 4, y + 4), label, fill=color)
    overlay.save(out_path, format="PNG")


def save_crops(image: Image.Image, regions: list[dict], out_dir: Path) -> None:
    for region in regions:
        x = int(region["x"])
        y = int(region["y"])
        w = int(region["width"])
        h = int(region["height"])
        crop = image.crop((x, y, x + w, y + h))
        suffix = region.get("type") or region.get("category") or "region"
        crop_path = out_dir / f"{region['id']}_{suffix}.png"
        crop.save(crop_path, format="PNG")


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-segment an architectural sheet (Option A + OCR).")
    parser.add_argument("input", help="Path to PDF or image (PNG/JPG).")
    parser.add_argument("--out-dir", default="tmp/auto_segments", help="Output directory.")
    parser.add_argument("--mode", choices=["cv", "layout", "detector"], default="cv")
    parser.add_argument("--dpi", type=int, default=400, help="PDF render DPI.")
    parser.add_argument("--max-dim", type=int, default=4200, help="Max dimension for detection.")
    parser.add_argument("--min-area-ratio", type=float, default=0.005)
    parser.add_argument("--merge-iou", type=float, default=0.20)
    parser.add_argument("--no-ocr", action="store_true")
    parser.add_argument("--ocr-lang", default="heb+eng")
    parser.add_argument("--tesseract-cmd", default="tesseract")
    parser.add_argument("--tessdata-dir", default=None)
    parser.add_argument("--include-ocr-text", action="store_true")
    parser.add_argument("--save-crops", action="store_true")
    parser.add_argument("--save-overlay", action="store_true")
    parser.add_argument("--deskew", action="store_true")

    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tessdata_dir = args.tessdata_dir
    if tessdata_dir is None:
        local_tessdata = Path(__file__).resolve().parent / "tessdata"
        if local_tessdata.exists():
            tessdata_dir = str(local_tessdata)

    config = SegmenterConfig(
        mode=args.mode,
        dpi=args.dpi,
        max_dim=args.max_dim,
        min_area_ratio=args.min_area_ratio,
        merge_iou_threshold=args.merge_iou,
        ocr_enabled=not args.no_ocr,
        ocr_lang=args.ocr_lang,
        tesseract_cmd=args.tesseract_cmd,
        tessdata_dir=tessdata_dir,
        include_ocr_text=args.include_ocr_text,
        deskew=args.deskew,
    )

    try:
        image = load_image(args.input, dpi=config.dpi)
        result = segment_image(image, config)
    except DependencyError as exc:
        print(f"Dependency error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Failed to segment: {exc}", file=sys.stderr)
        return 1

    json_path = out_dir / "segments.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=True, indent=2)

    if args.save_crops:
        crops_dir = out_dir / "crops"
        crops_dir.mkdir(parents=True, exist_ok=True)
        save_crops(image, result.get("regions", []), crops_dir)

    if args.save_overlay:
        overlay_path = out_dir / "overlay.png"
        save_overlay(image, result.get("regions", []), overlay_path)

    print(f"Wrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
