"""
Thumbnail generation service.

Handles thumbnail creation for images using Pillow:
- Resizes to 200px max dimension (maintains aspect ratio)
- Converts to WebP format for optimal compression
"""

import io
from typing import Any, BinaryIO, Optional

from src.logger.logger import Logger


try:
    from PIL import Image
    from PIL.Image import Image as ImageType
except ImportError:
    Image = None  # type: ignore
    ImageType = None  # type: ignore

# Thumbnail configuration
MAX_THUMBNAIL_DIMENSION = 200
THUMBNAIL_FORMAT = "webp"
THUMBNAIL_QUALITY = 85


class ThumbnailGenerationResult:
    """Result of thumbnail generation operation."""

    def __init__(
        self,
        success: bool,
        thumbnail_data: Optional[BinaryIO] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        error_message: Optional[str] = None,
    ):
        self.success = success
        self.thumbnail_data = thumbnail_data
        self.width = width
        self.height = height
        self.error_message = error_message


class ThumbnailService:
    """Service for generating image thumbnails."""

    @staticmethod
    def is_available() -> bool:
        """Check if Pillow is available for thumbnail generation."""
        return Image is not None

    @staticmethod
    def generate_thumbnail(
        image_data: BinaryIO,
        max_dimension: int = MAX_THUMBNAIL_DIMENSION,
    ) -> ThumbnailGenerationResult:
        """
        Generate a thumbnail from image data.

        Resizes the image to fit within max_dimension while maintaining aspect ratio,
        and converts to WebP format.

        Args:
            image_data: Binary image data (file-like object)
            max_dimension: Maximum width or height in pixels

        Returns:
            ThumbnailGenerationResult with thumbnail data or error
        """
        if not ThumbnailService.is_available():
            return ThumbnailGenerationResult(
                success=False,
                error_message="Pillow library not available for thumbnail generation",
            )

        try:
            # Open the image
            image: Any = Image.open(image_data)

            # Convert to RGB if necessary (e.g., for PNG with transparency)
            if image.mode in ("RGBA", "LA", "P"):
                # Create white background for transparency
                background = Image.new("RGB", image.size, (255, 255, 255))
                if image.mode == "P":
                    image = image.convert("RGBA")
                background.paste(
                    image,
                    mask=image.split()[-1] if image.mode in ("RGBA", "LA") else None,
                )
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")

            # Calculate thumbnail size maintaining aspect ratio
            width, height = image.size
            if width > height:
                new_width = min(width, max_dimension)
                new_height = int((new_width / width) * height)
            else:
                new_height = min(height, max_dimension)
                new_width = int((new_height / height) * width)

            # Resize image
            image.thumbnail((new_width, new_height), Image.Resampling.LANCZOS)

            # Save as WebP
            output = io.BytesIO()
            image.save(output, format=THUMBNAIL_FORMAT, quality=THUMBNAIL_QUALITY)
            output.seek(0)

            return ThumbnailGenerationResult(
                success=True,
                thumbnail_data=output,
                width=image.width,
                height=image.height,
            )
        except Exception as e:
            Logger.error(f"Failed to generate thumbnail: {e}")
            return ThumbnailGenerationResult(
                success=False,
                error_message=f"Thumbnail generation failed: {str(e)}",
            )


# Global instance
thumbnail_service = ThumbnailService()
