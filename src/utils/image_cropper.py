"""
Image cropping utilities for plan decomposition.
Extracts segments from full architectural plans using bounding boxes.
"""

from PIL import Image
from io import BytesIO
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class ImageCropper:
    """Crops segments from architectural plans using bounding box coordinates."""
    
    @staticmethod
    def crop_segment(
        image_path: str,
        bounding_box: dict,
        output_format: str = "PNG"
    ) -> BytesIO:
        """
        Crop a segment from a full plan image using bounding box coordinates.
        Automatically detects if coordinates are pixels or percentages.
        
        Args:
            image_path: Path to the full plan image
            bounding_box: Dict with keys: x, y, width, height
                         Values > 100 are treated as pixels, <= 100 as percentages
            output_format: Output image format (PNG, JPEG, etc.)
            
        Returns:
            BytesIO buffer with cropped image data
            
        Example:
            >>> # Percentage-based
            >>> bounding_box = {"x": 10, "y": 20, "width": 30, "height": 40}
            >>> cropped = ImageCropper.crop_segment("full_plan.png", bounding_box)
            >>> # Pixel-based
            >>> bounding_box = {"x": 110, "y": 233, "width": 486, "height": 294}
            >>> cropped = ImageCropper.crop_segment("full_plan.png", bounding_box)
        """
        try:
            # Load full image
            with Image.open(image_path) as img:
                img_width, img_height = img.size
                
                # Extract bounding box values
                x_val = bounding_box["x"]
                y_val = bounding_box["y"]
                width_val = bounding_box["width"]
                height_val = bounding_box["height"]
                
                # Detect if using pixels or percentages
                # If any value > 100, treat all as pixels
                use_pixels = any(val > 100 for val in [x_val, y_val, width_val, height_val])
                
                if use_pixels:
                    # Direct pixel coordinates
                    left = int(x_val)
                    top = int(y_val)
                    right = int(x_val + width_val)
                    bottom = int(y_val + height_val)
                    logger.info(f"Using pixel coordinates: ({left},{top})-({right},{bottom})")
                else:
                    # Convert percentage to pixels
                    left = int((x_val / 100) * img_width)
                    top = int((y_val / 100) * img_height)
                    right = int(((x_val + width_val) / 100) * img_width)
                    bottom = int(((y_val + height_val) / 100) * img_height)
                    logger.info(f"Converted percentage to pixels: ({left},{top})-({right},{bottom})")
                
                # Ensure coordinates are within image bounds
                left = max(0, min(left, img_width))
                top = max(0, min(top, img_height))
                right = max(0, min(right, img_width))
                bottom = max(0, min(bottom, img_height))
                
                # Validate crop region
                if left >= right or top >= bottom:
                    raise ValueError(
                        f"Invalid crop region: left={left}, top={top}, right={right}, bottom={bottom}. "
                        f"Image size: {img_width}x{img_height}"
                    )
                
                # Crop the segment
                cropped = img.crop((left, top, right, bottom))
                
                # Save to BytesIO buffer
                buffer = BytesIO()
                cropped.save(buffer, format=output_format)
                buffer.seek(0)
                
                logger.info(
                    f"Cropped segment: bbox={bounding_box} -> "
                    f"pixels ({left},{top})-({right},{bottom}), "
                    f"size {cropped.size}, mode={'pixels' if use_pixels else 'percentages'}"
                )
                
                return buffer
                
        except Exception as e:
            logger.error(f"Failed to crop segment: {e}")
            raise
    
    @staticmethod
    def create_thumbnail(
        image_buffer: BytesIO,
        max_size: Tuple[int, int] = (300, 200),
        output_format: str = "PNG"
    ) -> BytesIO:
        """
        Create a thumbnail from an image buffer.
        
        Args:
            image_buffer: BytesIO buffer with image data
            max_size: Maximum thumbnail size (width, height)
            output_format: Output image format
            
        Returns:
            BytesIO buffer with thumbnail data
        """
        try:
            image_buffer.seek(0)
            with Image.open(image_buffer) as img:
                # Create thumbnail (maintains aspect ratio)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                # Save to new buffer
                thumb_buffer = BytesIO()
                img.save(thumb_buffer, format=output_format)
                thumb_buffer.seek(0)
                
                logger.info(f"Created thumbnail: size {img.size}")
                
                return thumb_buffer
                
        except Exception as e:
            logger.error(f"Failed to create thumbnail: {e}")
            raise
    
    @staticmethod
    def get_image_dimensions(image_path: str) -> Tuple[int, int]:
        """
        Get image dimensions without loading the full image into memory.
        
        Args:
            image_path: Path to image file
            
        Returns:
            Tuple of (width, height)
        """
        try:
            with Image.open(image_path) as img:
                return img.size
        except Exception as e:
            logger.error(f"Failed to get image dimensions: {e}")
            raise
    
    @staticmethod
    def crop_and_create_thumbnail(
        image_path: str,
        bounding_box: dict,
        thumbnail_size: Tuple[int, int] = (300, 200),
        output_format: str = "PNG"
    ) -> Tuple[BytesIO, BytesIO]:
        """
        Crop a segment and create its thumbnail in one operation.
        
        Args:
            image_path: Path to the full plan image
            bounding_box: Dict with bounding box coordinates
            thumbnail_size: Maximum thumbnail size
            output_format: Output image format
            
        Returns:
            Tuple of (cropped_buffer, thumbnail_buffer)
        """
        try:
            # Crop the segment
            cropped_buffer = ImageCropper.crop_segment(
                image_path, bounding_box, output_format
            )
            
            # Create thumbnail from cropped image
            thumb_buffer = ImageCropper.create_thumbnail(
                cropped_buffer, thumbnail_size, output_format
            )
            
            # Reset cropped buffer position
            cropped_buffer.seek(0)
            
            return cropped_buffer, thumb_buffer
            
        except Exception as e:
            logger.error(f"Failed to crop and create thumbnail: {e}")
            raise


def get_image_cropper() -> ImageCropper:
    """Get singleton ImageCropper instance."""
    return ImageCropper()
