"""
Border detection utilities to refine GPT's bounding boxes.
Uses computer vision to snap to actual rectangular frames.
"""

import cv2
import numpy as np
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class BorderDetector:
    """Detects and refines rectangular borders in architectural drawings."""
    
    @staticmethod
    def refine_bounding_box(
        image_path: str,
        bbox: dict,
        search_margin: int = 50
    ) -> dict:
        """
        Refine a bounding box by finding actual rectangular borders near GPT's estimate.
        
        Args:
            image_path: Path to the image file
            bbox: Dictionary with x, y, width, height (GPT's estimate)
            search_margin: How many pixels to search beyond GPT's box for borders
            
        Returns:
            Refined bounding box dictionary (or original if no clear border found)
        """
        try:
            # Read image
            img = cv2.imread(image_path)
            if img is None:
                logger.warning(f"Could not read image: {image_path}")
                return bbox
            
            img_height, img_width = img.shape[:2]
            
            # Extract GPT's estimated region
            x = int(bbox.get('x', 0))
            y = int(bbox.get('y', 0))
            width = int(bbox.get('width', 100))
            height = int(bbox.get('height', 100))
            
            # Define search area (GPT's box + margin)
            search_x = max(0, x - search_margin)
            search_y = max(0, y - search_margin)
            search_x2 = min(img_width, x + width + search_margin)
            search_y2 = min(img_height, y + height + search_margin)
            
            # Crop search region
            search_region = img[search_y:search_y2, search_x:search_x2]
            
            # Convert to grayscale
            gray = cv2.cvtColor(search_region, cv2.COLOR_BGR2GRAY)
            
            # Apply edge detection
            edges = cv2.Canny(gray, 50, 150, apertureSize=3)
            
            # Find contours
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if not contours:
                logger.info("No contours found, using original bbox")
                return bbox
            
            # Find the largest rectangular contour that overlaps with GPT's estimate
            best_rect = None
            best_area = 0
            
            for contour in contours:
                # Approximate contour to polygon
                epsilon = 0.02 * cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, epsilon, True)
                
                # Look for rectangles (4 corners)
                if len(approx) == 4:
                    rect_x, rect_y, rect_w, rect_h = cv2.boundingRect(contour)
                    area = rect_w * rect_h
                    
                    # Check if this rectangle overlaps with GPT's estimate
                    gpt_center_x = (x - search_x) + width / 2
                    gpt_center_y = (y - search_y) + height / 2
                    
                    if (rect_x <= gpt_center_x <= rect_x + rect_w and
                        rect_y <= gpt_center_y <= rect_y + rect_h and
                        area > best_area):
                        best_rect = (rect_x, rect_y, rect_w, rect_h)
                        best_area = area
            
            # If we found a good rectangular border, use it
            if best_rect:
                rect_x, rect_y, rect_w, rect_h = best_rect
                refined_bbox = {
                    'x': search_x + rect_x,
                    'y': search_y + rect_y,
                    'width': rect_w,
                    'height': rect_h
                }
                
                logger.info(
                    f"Border refined: "
                    f"original=({x},{y},{width},{height}) -> "
                    f"refined=({refined_bbox['x']},{refined_bbox['y']},{refined_bbox['width']},{refined_bbox['height']})"
                )
                
                return refined_bbox
            else:
                logger.info("No suitable rectangular border found, using original bbox")
                return bbox
                
        except Exception as e:
            logger.error(f"Border refinement failed: {e}")
            return bbox


def get_border_detector() -> BorderDetector:
    """Get singleton BorderDetector instance."""
    return BorderDetector()
