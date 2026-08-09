from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from app.modules.ingestion.application.parsers import safe_filename

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_DIMENSION = 12_000
MAX_IMAGE_PIXELS = 40_000_000


@dataclass(frozen=True, slots=True)
class ValidatedImage:
    filename: str
    content_type: str
    extension: str
    checksum_sha256: str
    width: int
    height: int
    data: bytes


def validate_image(
    filename: str, declared_content_type: str, data: bytes
) -> ValidatedImage:
    name = safe_filename(filename)
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Image must contain at most 10 MiB of data.")
    formats = {
        "JPEG": ("image/jpeg", ".jpg"),
        "PNG": ("image/png", ".png"),
        "WEBP": ("image/webp", ".webp"),
        "AVIF": ("image/avif", ".avif"),
    }
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = image.format
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as error:
        raise ValueError("Image content is invalid.") from error
    if image_format not in formats:
        raise ValueError("Image format is not supported.")
    content_type, extension = formats[image_format]
    if declared_content_type and declared_content_type != content_type:
        raise ValueError("Image content type does not match its content.")
    if (
        width <= 0
        or height <= 0
        or width > MAX_IMAGE_DIMENSION
        or height > MAX_IMAGE_DIMENSION
        or width * height > MAX_IMAGE_PIXELS
    ):
        raise ValueError("Image dimensions are outside the supported limits.")
    return ValidatedImage(
        filename=name,
        content_type=content_type,
        extension=extension,
        checksum_sha256=hashlib.sha256(data).hexdigest(),
        width=width,
        height=height,
        data=data,
    )
